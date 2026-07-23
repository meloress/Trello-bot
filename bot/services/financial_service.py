"""8.6-band: moliyaviy javobgarlik TAKLIFLARI (bayroqlash + summa hisob-kitobi).

Bu servis HECH QACHON pul ko'chirmaydi, maoshni o'zgartirmaydi, mijozga xabar
yubormaydi — faqat SON hisoblab, `FinancialSuggestion` yozuvini `PENDING_
MANAGER_REVIEW` holatida saqlaydi. Tasdiqlash/rad etish (approve/reject)
INSON tomonidan, BOSHQA modulda amalga oshiriladi — bu yerda faqat interfeys
(`status` maydoni) tayyor.

Ikkita mustaqil qoida (TZ 8.6-band):
- 1-qoida (wage deduction): bo'lim aybi bilan mijozdan to'liq to'lov
  olinmasa va bo'lim shu bosqichda ko'p vaqt o'tkazgan bo'lsa.
- 2-qoida (advance waiver): 80%+ avans olingandan keyin muddat o'tkazilsa,
  qolgan foiz mijozdan talab qilinmaydi.

Ikkalasi ham hisoblash uchun mijoz to'lovi/avans/buyurtma summasi kabi
ma'lumotni talab qiladi — bu tizimda moliya moduli yo'q (TZ 18-band), shuning
uchun bu qiymatlar HAR DOIM tashqaridan (kelajakdagi admin UI) qo'lda
kiritiladi; faqat bosqich davomiyligi (`stage_duration_days`) avtomatik
hisoblanadi (`overdue_watch_job` orqali, pastga qarang).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from core.database import async_session
from db.models.financial_suggestion import FinancialSuggestion
from db.repositories import FinancialSuggestionRepository, TaskRepository
from services import settings_service
from utils.enums import FinancialSuggestionKind, FinancialSuggestionStatus


@dataclass(frozen=True)
class WageDeductionSuggestion:
    applicable: bool
    suggested_deduction_amount: float | None
    status: str


@dataclass(frozen=True)
class AdvanceWaiverSuggestion:
    applicable: bool
    waived_amount: float | None
    status: str


@dataclass(frozen=True)
class SpeedTierSuggestion:
    applicable: bool
    tier: str | None
    suggested_pay_amount: float | None
    status: str


def calculate_wage_deduction_suggestion(
    *, stage_duration_days: int, threshold_days: int, amount_withheld_by_customer: float | None
) -> WageDeductionSuggestion:
    """8.6-band 1-qoida (sof funksiya, DB'ga tegmaydi). `applicable` faqat
    bosqich davomiyligi chegaradan ORTIQ (qat'iy >) bo'lishiga bog'liq;
    summa hali noma'lum bo'lsa `suggested_deduction_amount=None` ("kutilmoqda"),
    ma'lum bo'lsa 50% (dumaloqlashtirilmasdan — chaqiruvchi tomon dumaloqlaydi)."""
    applicable = stage_duration_days > threshold_days
    suggested = None
    if applicable and amount_withheld_by_customer is not None:
        suggested = amount_withheld_by_customer * 0.5
    return WageDeductionSuggestion(
        applicable=applicable,
        suggested_deduction_amount=suggested,
        status=FinancialSuggestionStatus.PENDING_MANAGER_REVIEW.value,
    )


def calculate_advance_waiver(
    *,
    advance_percent_paid: int,
    is_late: bool,
    order_total_value: float,
    advance_threshold_percent: int,
    waiver_percent: int,
) -> AdvanceWaiverSuggestion:
    """8.6-band 2-qoida (sof funksiya). `applicable` = avans chegaradan
    KO'P/TENG olingan VA buyurtma kechikkan bo'lsa."""
    applicable = advance_percent_paid >= advance_threshold_percent and is_late
    waived = order_total_value * (waiver_percent / 100) if applicable else None
    return AdvanceWaiverSuggestion(
        applicable=applicable,
        waived_amount=waived,
        status=FinancialSuggestionStatus.PENDING_MANAGER_REVIEW.value,
    )


def calculate_speed_tier_bonus(
    *, stage_duration_days: int, schedule: list[dict], base_pay_amount: float | None
) -> SpeedTierSuggestion:
    """Fasad sex TZ, Phase 7 (sof funksiya, DB'ga tegmaydi). Jadval bo'sh
    bo'lsa — mexanizm hali sozlanmagan, `applicable=False`. Bo'sh bo'lmasa,
    haqiqiy davomiylik hali ham SIG'ADIGAN eng tor tier tanlanadi (eng kichik
    `max_days >= stage_duration_days`) — masalan 3 kunlik jadvalda 2 kunlik
    bosqich `max_days=3`ga tushadi, `max_days=1`ga emas. Hech qaysi tier
    sig'masa (davomiylik hammasidan uzoq) — `applicable=False` (eng sekin
    tierga avtomatik tushirilmaydi, bu his qilinmagan biznes qoida bo'lardi).
    `base_pay_amount=None` bo'lsa (bugungi kunda tizimda maosh maydoni yo'q)
    `tier` baribir aniqlanadi, faqat `suggested_pay_amount=None` qoladi."""
    if not schedule:
        return SpeedTierSuggestion(
            applicable=False,
            tier=None,
            suggested_pay_amount=None,
            status=FinancialSuggestionStatus.PENDING_MANAGER_REVIEW.value,
        )

    matched = min(
        (entry for entry in schedule if entry["max_days"] >= stage_duration_days),
        key=lambda entry: entry["max_days"],
        default=None,
    )
    if matched is None:
        return SpeedTierSuggestion(
            applicable=False,
            tier=None,
            suggested_pay_amount=None,
            status=FinancialSuggestionStatus.PENDING_MANAGER_REVIEW.value,
        )

    suggested_pay_amount = base_pay_amount * matched["pay_multiplier"] if base_pay_amount is not None else None
    return SpeedTierSuggestion(
        applicable=True,
        tier=matched["tier"],
        suggested_pay_amount=suggested_pay_amount,
        status=FinancialSuggestionStatus.PENDING_MANAGER_REVIEW.value,
    )


async def flag_long_duration_stage(task_id: int) -> FinancialSuggestion | None:
    """`overdue_watch_job` tomonidan soatiga chaqiriladi: bosqich sozlangan
    `financial_flag_threshold_days`dan ortiq davom etsa va bu vazifa uchun
    hali WAGE_DEDUCTION taklifi yozilmagan bo'lsa, summa hali noma'lum
    (`amount_withheld_by_customer=None`) holatda yozuv yaratadi — kelajakdagi
    admin UI summani keyin to'ldiradi. Applicable bo'lmasa yoki allaqachon
    bayroqlangan bo'lsa `None` qaytaradi (xatolik emas)."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        suggestion_repo = FinancialSuggestionRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            return None
        if await suggestion_repo.exists_for_task(task_id, FinancialSuggestionKind.WAGE_DEDUCTION):
            return None

        threshold_days = (await settings_service.get_settings()).financial_flag_threshold_days
        stage_duration_days = (datetime.now(timezone.utc) - task.started_at).days
        result = calculate_wage_deduction_suggestion(
            stage_duration_days=stage_duration_days,
            threshold_days=threshold_days,
            amount_withheld_by_customer=None,
        )
        if not result.applicable:
            return None

        suggestion = await suggestion_repo.create(
            task_id=task_id,
            kind=FinancialSuggestionKind.WAGE_DEDUCTION,
            status=result.status,
            applicable=result.applicable,
            stage_duration_days=stage_duration_days,
            amount_withheld_by_customer=None,
            suggested_deduction_amount=None,
        )
        await session.commit()
        return suggestion


async def set_wage_deduction_amount(suggestion_id: int, amount_withheld_by_customer: float) -> FinancialSuggestion:
    """8.6-band 1-qoida admin UI: avtomatik bayroqlangan (summasi hali `NULL`)
    taklifga admin qo'lda mijoz ushlab qolgan summani kiritganda chaqiriladi
    — `suggested_deduction_amount` shu asosda (`* 0.5`) qayta hisoblanadi."""
    async with async_session() as session:
        repo = FinancialSuggestionRepository(session)
        suggestion = await repo.get_by_id(suggestion_id)
        if suggestion is None:
            raise ValueError(f"FinancialSuggestion {suggestion_id} topilmadi")

        await repo.update(
            suggestion,
            amount_withheld_by_customer=amount_withheld_by_customer,
            suggested_deduction_amount=amount_withheld_by_customer * 0.5,
        )
        await session.commit()
        return suggestion


async def create_advance_waiver_suggestion(
    task_id: int, *, advance_percent_paid: int, is_late: bool, order_total_value: float
) -> FinancialSuggestion:
    """8.6-band 2-qoida: avtomatik ma'lumot manbai yo'q (avans/buyurtma
    summasi tizimda umuman saqlanmaydi), shuning uchun `overdue_watch_job`dan
    CHAQIRILMAYDI — faqat kelajakdagi admin UI (hali qurilmagan) tomonidan
    qo'lda kiritilgan qiymatlar bilan chaqirilishga tayyor interfeys."""
    settings = await settings_service.get_settings()
    result = calculate_advance_waiver(
        advance_percent_paid=advance_percent_paid,
        is_late=is_late,
        order_total_value=order_total_value,
        advance_threshold_percent=settings.advance_threshold_percent,
        waiver_percent=settings.advance_waiver_percent,
    )
    async with async_session() as session:
        suggestion = await FinancialSuggestionRepository(session).create(
            task_id=task_id,
            kind=FinancialSuggestionKind.ADVANCE_WAIVER,
            status=result.status,
            applicable=result.applicable,
            advance_percent_paid=advance_percent_paid,
            order_total_value=order_total_value,
            waived_amount=result.waived_amount,
        )
        await session.commit()
        return suggestion


async def suggest_speed_tier_bonus(task_id: int) -> FinancialSuggestion | None:
    """Fasad sex TZ, Phase 7: bosqich yakunlanganda (`miniapp/api/worker.py`'s
    `finish_task`) chaqiriladi. Davomiylik `finished_at - started_at`dan
    hisoblanadi — `flag_long_duration_stage`dagi bilan bir xil `.days`
    kesish qoidasi. Idempotentlik `exists_for_task` orqali (bir xil task
    uchun ikkinchi marta chaqirilsa yozuv yaratilmaydi). `base_pay_amount`
    tizimda hech qanday maosh/stavka maydoni yo'qligi sabab doim `None`
    (`calculate_speed_tier_bonus` shunda ham to'g'ri `tier`ni aniqlaydi)."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        suggestion_repo = FinancialSuggestionRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None or task.finished_at is None:
            return None
        if await suggestion_repo.exists_for_task(task_id, FinancialSuggestionKind.SPEED_TIER_BONUS):
            return None

        schedule = (await settings_service.get_settings()).speed_tier_schedule
        stage_duration_days = (task.finished_at - task.started_at).days
        result = calculate_speed_tier_bonus(
            stage_duration_days=stage_duration_days,
            schedule=schedule,
            base_pay_amount=None,
        )
        if not result.applicable:
            return None

        suggestion = await suggestion_repo.create(
            task_id=task_id,
            kind=FinancialSuggestionKind.SPEED_TIER_BONUS,
            status=result.status,
            applicable=result.applicable,
            speed_tier=result.tier,
            suggested_pay_amount=result.suggested_pay_amount,
        )
        await session.commit()
        return suggestion


async def set_speed_tier_pay_amount(suggestion_id: int, suggested_pay_amount: float) -> FinancialSuggestion:
    """Admin UI: `tier` avtomatik aniqlangan, lekin summa hali noma'lum
    (`base_pay_amount=None` bo'lgani uchun) takliflarga admin qo'lda to'lov
    summasini kiritganda chaqiriladi — `set_wage_deduction_amount`dagi bilan
    bir xil naqsh, faqat ko'paytiruvchi qayta hisoblanmaydi (admin to'g'ridan-
    to'g'ri yakuniy summani kiritadi)."""
    async with async_session() as session:
        repo = FinancialSuggestionRepository(session)
        suggestion = await repo.get_by_id(suggestion_id)
        if suggestion is None:
            raise ValueError(f"FinancialSuggestion {suggestion_id} topilmadi")

        await repo.update(suggestion, suggested_pay_amount=suggested_pay_amount)
        await session.commit()
        return suggestion
