"""KPI: minus/plus ball va jarima tizimi (8-band).

`timer_service.py` uslubiga mos: har funksiya o'z sessiyasini ochib-yopadi va
oxirida commit qiladi (Unit of Work). ORM obyektlari to'g'ridan-to'g'ri
qaytariladi (`core/database.py`dagi `expire_on_commit=False` tufayli xavfsiz).

Sozlanuvchan bo'lishi SHART bo'lgan qiymatlar (16-band):
- kechikish jadvali (8.2) — bazadagi `penalty_rules` jadvalida (har xil
  oraliqlar uchun turli qatorlar kerak bo'lgani sabab, alohida jadval);
- yagona skalyar qiymatlar (jarima ko'paytiruvchisi, brigadir ulushi,
  kun-siljish balli) — `services/settings_service.py` orqali (`app_settings`
  SINGLETON jadvali, keshlangan holda o'qiladi).
Hech biri kodga hardcode qilinmagan.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from core.database import async_session
from db.models.brigade import Brigade
from db.models.employee import Employee
from db.models.kpi_log import KpiLog
from db.repositories import (
    BrigadeRepository,
    EmployeeRepository,
    KpiLogRepository,
    PenaltyRuleRepository,
    TaskAssignmentRepository,
    TaskRepository,
)
from services import settings_service
from utils.enums import Role

logger = logging.getLogger(__name__)

# 8.5-band: bazaviy to'lov/avans kuni (har oyning shu sanasi). Bu qiymat
# 16-banddagi sozlanuvchan ro'yxatda (remind_time, default_penalty_multiplier,
# brigade_share_ratio, balls_per_day_shift) yo'q, shuning uchun hozircha
# konstanta bo'lib qoladi.
BASE_PAYMENT_DAY = 15


class TaskNotFoundError(Exception):
    """Berilgan task_id bo'yicha vazifa topilmadi."""


class EmployeeNotFoundError(Exception):
    """Berilgan employee_id bo'yicha xodim topilmadi."""


class InvalidTaskStateError(Exception):
    """So'ralgan amal vazifaning joriy holatiga mos kelmaydi."""


class PenaltyRuleNotConfiguredError(Exception):
    """Berilgan kechikish uchun penalty_rules'da mos qoida topilmadi (admin hali qo'shmagan)."""


def _month_bounds(reference: date) -> tuple[datetime, datetime]:
    """[oy boshi 00:00, keyingi oy boshi 00:00) — yarim ochiq oraliq (UTC)."""
    start = datetime(reference.year, reference.month, 1, tzinfo=timezone.utc)
    if reference.month == 12:
        end = datetime(reference.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(reference.year, reference.month + 1, 1, tzinfo=timezone.utc)
    return start, end


async def _write_scores_for_employees(
    session, *, employee_ids: list[int], score: int, reason: str, task_id: int, brigade_share_ratio: float
) -> list[KpiLog]:
    """Minus (kechikish) va plus (muddatdan oldin) yo'llarining ikkalasi ham
    shu umumiy yadrodan foydalanadi: berilgan employee_id ro'yxatidagi ISHCHI
    (Role.WORKER) xodimlarning har biriga bir xil `score`ni yozadi, har biri
    uchun 8.4-band bo'yicha brigadir ulushini ham qo'shadi (ulush ikki
    yo'nalishda ham ishlaydi — `score` musbat bo'lsa bonus ulushi, manfiy
    bo'lsa jarima ulushi, `_apply_brigade_share_for_worker` sof arifmetika)."""
    employee_repo = EmployeeRepository(session)
    brigade_repo = BrigadeRepository(session)
    kpi_repo = KpiLogRepository(session)

    created_logs: list[KpiLog] = []
    for employee_id in employee_ids:
        employee = await employee_repo.get_by_id(employee_id)
        if employee is None or employee.role != Role.WORKER:
            continue

        log = await kpi_repo.create(employee_id=employee_id, score=score, reason=reason)
        created_logs.append(log)

        brigadier_log = await _apply_brigade_share_for_worker(
            brigade_repo,
            employee_repo,
            kpi_repo,
            worker=employee,
            worker_score=score,
            ratio=brigade_share_ratio,
            task_id=task_id,
        )
        if brigadier_log is not None:
            created_logs.append(brigadier_log)

    return created_logs


async def apply_penalty_for_employees(
    *, task_id: int, department_id: int | None, employee_ids: list[int], hours_late: int, reason_label: str
) -> list[KpiLog]:
    """8.1/8.2-band jarima yozish mantig'ining umumiy yadrosi — muddatida
    yakunlangan vazifa (`calculate_and_apply_task_penalty`) va 8.3-band
    "brigadaga o'tkazish"da eski brigadaga DARHOL jarima
    (`task_service.reassign_task_brigade`) ikkalasi ham shundan foydalanadi.
    `penalty_rules`dan mos qoidani topib, ISHCHI (Role.WORKER) rolidagi
    xodim(lar)ga to'liq jarimani yozadi, har biriga 8.4-band bo'yicha
    brigadir ulushini ham qo'shadi."""
    async with async_session() as session:
        rule_repo = PenaltyRuleRepository(session)

        rule = await rule_repo.find_applicable_rule(hours_late, department_id)
        if rule is None:
            raise PenaltyRuleNotConfiguredError(
                f"Task {task_id}: {hours_late} soat kechikish uchun penalty_rules'da mos qoida yo'q"
            )

        app_settings = await settings_service.get_settings()
        final_score = round(rule.score * app_settings.default_penalty_multiplier)

        created_logs = await _write_scores_for_employees(
            session,
            employee_ids=employee_ids,
            score=final_score,
            reason=f"{reason_label}: {hours_late} soat (vazifa #{task_id})",
            task_id=task_id,
            brigade_share_ratio=app_settings.brigade_share_ratio,
        )
        await session.commit()
        result_employee_ids = [log.employee_id for log in created_logs]

    for employee_id in result_employee_ids:
        await update_payment_date_if_needed(employee_id)

    return created_logs


async def apply_plus_ball_for_employees(*, task_id: int, employee_ids: list[int], hours_early: int) -> list[KpiLog]:
    """8.4-band: `calculate_and_apply_task_penalty()` muddatdan OLDIN tugagan
    vazifa uchun chaqiradi. `calculate_plus_ball()` 0 qaytarsa (masalan
    24 soatlik "grace period"dan kam bo'lsa) hech narsa yozmaydi."""
    plus_score = await calculate_plus_ball(hours_early)
    if plus_score == 0:
        return []

    async with async_session() as session:
        app_settings = await settings_service.get_settings()
        created_logs = await _write_scores_for_employees(
            session,
            employee_ids=employee_ids,
            score=plus_score,
            reason=f"Muddatdan oldin tugatish: {hours_early} soat oldin (vazifa #{task_id})",
            task_id=task_id,
            brigade_share_ratio=app_settings.brigade_share_ratio,
        )
        await session.commit()
        result_employee_ids = [log.employee_id for log in created_logs]

    for employee_id in result_employee_ids:
        await update_payment_date_if_needed(employee_id)

    return created_logs


async def calculate_and_apply_task_penalty(task_id: int) -> list[KpiLog]:
    """8.1/8.2/8.4-band: vazifa yakunlanganda chaqiriladi.
    - Muddatidan KECH tugagan bo'lsa: 24 soatlik "grace period"dan keyin
      (`hours_late < 24` bo'lsa hech narsa yozilmaydi — bu `penalty_rules`
      jadvalidagi bracket'lar endi 24 soatdan boshlangani uchun tabiiy kelib
      chiqadi) `apply_penalty_for_employees()` orqali jarima.
    - Aniq MUDDATIDA tugagan bo'lsa: bo'sh ro'yxat, hech narsa yozilmaydi.
    - Muddatidan OLDIN tugagan bo'lsa: `apply_plus_ball_for_employees()`
      orqali 8.4-band plus balli.

    8.3-band: agar buyurtma brigadaga o'tkazilgan bo'lsa (`task.reassigned_at`
    NOT NULL), kechikish shu paytdan hisoblanadi (`deadline`dan emas) — eski
    brigada allaqachon `reassign_task_brigade()`da jarimalangan davrni yangi
    brigadaga qayta hisoblamaslik uchun."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.finished_at is None:
            raise InvalidTaskStateError(f"Task {task_id} hali yakunlanmagan")

        reference_start = task.reassigned_at or task.deadline
        delta_seconds = (task.finished_at - reference_start).total_seconds()
        department_id = task.current_department_id
        employee_ids = [a.employee_id for a in await assignment_repo.list_by_task(task_id)]

    if delta_seconds == 0:
        return []

    if delta_seconds < 0:
        hours_early = int(-delta_seconds // 3600)
        return await apply_plus_ball_for_employees(task_id=task_id, employee_ids=employee_ids, hours_early=hours_early)

    hours_late = int(delta_seconds // 3600)
    if hours_late < 24:
        return []  # 8.1/8.2-band: 24 soatlik grace period, dayIndex=0 -> jarima yo'q

    return await apply_penalty_for_employees(
        task_id=task_id,
        department_id=department_id,
        employee_ids=employee_ids,
        hours_late=hours_late,
        reason_label="Kechikish",
    )


async def _apply_brigade_share_for_worker(
    brigade_repo: BrigadeRepository,
    employee_repo: EmployeeRepository,
    kpi_repo: KpiLogRepository,
    *,
    worker: Employee,
    worker_score: int,
    ratio: float,
    task_id: int,
) -> KpiLog | None:
    """8.4-band: `worker` ball olganda (bonus/jarima), uning brigadiriga ulush
    yozadi. Brigadasi yo'q, brigadaning brigadiri tayinlanmagan, yoki ulush
    0'ga yaxlitlansa — jim `None` qaytaradi (xatolik emas)."""
    if worker.brigade_id is None:
        return None

    brigade: Brigade | None = await brigade_repo.get_by_id(worker.brigade_id)
    if brigade is None or brigade.brigadier_id is None or brigade.brigadier_id == worker.id:
        return None

    brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
    if brigadier is None:
        return None

    if brigadier.telegram_id is None:
        logger.warning(
            "Brigadir '%s' (id=%s) uchun telegram_id yo'q — ulush baribir kpi_logs'ga yoziladi, "
            "lekin bildirishnoma yetib bormaydi",
            brigadier.full_name,
            brigadier.id,
        )

    share_score = round(await apply_brigade_share(worker_score, ratio))
    if share_score == 0:
        return None

    return await kpi_repo.create(
        employee_id=brigadier.id,
        score=share_score,
        reason=f"Brigada ulushi: {worker.full_name}ning bali {worker_score:+d} (vazifa #{task_id})",
    )


async def add_manual_kpi(employee_id: int, score: int, reason: str) -> KpiLog:
    """Admin/nazoratchi tomonidan qo'lda bonus (musbat) yoki jarima (manfiy) yozish."""
    if not reason or not reason.strip():
        raise ValueError("Sabab (reason) bo'sh bo'lishi mumkin emas")
    if score == 0:
        raise ValueError("score 0 bo'lishi mumkin emas")

    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        kpi_repo = KpiLogRepository(session)

        employee = await employee_repo.get_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundError(f"Employee {employee_id} topilmadi")

        kpi_log = await kpi_repo.create(employee_id=employee_id, score=score, reason=reason)
        await session.commit()

    if score < 0:
        await update_payment_date_if_needed(employee_id)

    return kpi_log


async def calculate_total_score(
    employee_id: int, *, since: datetime | None = None, until: datetime | None = None
) -> int:
    """Berilgan davr (default: joriy oy, [since, until)) uchun xodimning jami KPI
    balli. Faqat o'qiydi — yozuv yo'q, shuning uchun commit qilinmaydi."""
    if since is None or until is None:
        month_start, month_end = _month_bounds(datetime.now(timezone.utc).date())
        since = since or month_start
        until = until or month_end

    async with async_session() as session:
        logs = await KpiLogRepository(session).list_by_employee_in_range(employee_id, since, until)

    return sum(log.score for log in logs)


async def calculate_monthly_rollup(employee_id: int, *, month: str) -> tuple[int, int]:
    """Statistika uchun: `calculate_total_score()`dan farqli o'laroq, oylik
    minus va plus ballarni ALOHIDA qaytaradi (bitta "net" songa qo'shilmaydi —
    xodim qancha jarima va qancha bonus olganini alohida ko'rish kerak bo'lgan
    hisobotlar uchun, masalan 4-bosqich dashboard). `month`: "YYYY-MM" formatida.

    Qaytaradi: (monthly_minus, monthly_plus) — ikkalasi ham 0 yoki musbat son
    (monthly_minus manfiy ballarning yig'indisi ABSOLYUT qiymatda EMAS, balki
    o'z ishorasi bilan, ya'ni <= 0)."""
    year, mon = (int(part) for part in month.split("-"))
    since, until = _month_bounds(date(year, mon, 1))

    async with async_session() as session:
        logs = await KpiLogRepository(session).list_by_employee_in_range(employee_id, since, until)

    monthly_minus = sum(log.score for log in logs if log.score < 0)
    monthly_plus = sum(log.score for log in logs if log.score > 0)
    return monthly_minus, monthly_plus


async def update_payment_date_if_needed(employee_id: int) -> Employee:
    """8.5-band: joriy oyda to'plangan minus ballarga qarab to'lov/avans kunini
    qayta hisoblaydi. Har chaqirilganda joriy oy ma'lumotlaridan NOLDAN qayta
    hisoblanadi (idempotent) — shu sababli alohida "oylik reset" job kerak emas:
    oy almashgach, `_month_bounds` avtomatik ravishda yangi oyni ko'radi."""
    month_start, month_end = _month_bounds(datetime.now(timezone.utc).date())

    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        kpi_repo = KpiLogRepository(session)

        employee = await employee_repo.get_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundError(f"Employee {employee_id} topilmadi")

        logs = await kpi_repo.list_by_employee_in_range(employee_id, month_start, month_end)
        total_minus = sum(-log.score for log in logs if log.score < 0)
        balls_per_day_shift = (await settings_service.get_settings()).balls_per_day_shift
        shift_days = total_minus // balls_per_day_shift

        new_payment_date = date(month_start.year, month_start.month, BASE_PAYMENT_DAY) + timedelta(
            days=shift_days
        )

        if employee.next_payment_date != new_payment_date:
            await employee_repo.update(employee, next_payment_date=new_payment_date)
            await session.commit()

        return employee


async def calculate_plus_ball(hours_early: int) -> int:
    """8.4-band: muddatdan `hours_early` soat oldin tugatilgan bo'lsa, necha
    ball berilishini hisoblaydi. Yondashuv (foydalanuvchi tasdiqlagan): faqat
    muddatdan oldin tugatish mezon, sifat/nazoratchi tasdig'i shart emas.
    dayIndex = hours_early // 24 (necha TO'LIQ kun oldin) — har kuni
    `plus_ball_per_day` ball, `plus_ball_max_days`dan ortiq kun uchun
    qo'shimcha ball berilmaydi (cap, ikkalasi ham /settings orqali sozlanadi)."""
    if hours_early <= 0:
        return 0

    day_index = hours_early // 24
    app_settings = await settings_service.get_settings()
    capped_days = min(day_index, app_settings.plus_ball_max_days)
    return capped_days * app_settings.plus_ball_per_day


async def apply_brigade_share(worker_score: int, ratio: float | None = None) -> float:
    """8.4-band: ishchining minus balidan brigadirga o'tadigan ulushni hisoblaydi
    (faqat arifmetika — kimning brigadiri ekanini aniqlamaydi, chaqiruvchi
    aniqlaydi). `ratio` berilmasa, `settings_service`dagi joriy
    `brigade_share_ratio` ishlatiladi (admin `/settings` orqali o'zgartirgan)."""
    if ratio is None:
        ratio = (await settings_service.get_settings()).brigade_share_ratio
    return worker_score * ratio
