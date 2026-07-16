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
        employee_repo = EmployeeRepository(session)
        brigade_repo = BrigadeRepository(session)
        kpi_repo = KpiLogRepository(session)

        rule = await rule_repo.find_applicable_rule(hours_late, department_id)
        if rule is None:
            raise PenaltyRuleNotConfiguredError(
                f"Task {task_id}: {hours_late} soat kechikish uchun penalty_rules'da mos qoida yo'q"
            )

        app_settings = await settings_service.get_settings()
        final_score = round(rule.score * app_settings.default_penalty_multiplier)

        created_logs: list[KpiLog] = []
        for employee_id in employee_ids:
            employee = await employee_repo.get_by_id(employee_id)
            if employee is None or employee.role != Role.WORKER:
                continue

            log = await kpi_repo.create(
                employee_id=employee_id,
                score=final_score,
                reason=f"{reason_label}: {hours_late} soat (vazifa #{task_id})",
            )
            created_logs.append(log)

            brigadier_log = await _apply_brigade_share_for_worker(
                brigade_repo,
                employee_repo,
                kpi_repo,
                worker=employee,
                worker_score=final_score,
                ratio=app_settings.brigade_share_ratio,
                task_id=task_id,
            )
            if brigadier_log is not None:
                created_logs.append(brigadier_log)

        await session.commit()
        result_employee_ids = [log.employee_id for log in created_logs]

    for employee_id in result_employee_ids:
        await update_payment_date_if_needed(employee_id)

    return created_logs


async def calculate_and_apply_task_penalty(task_id: int) -> list[KpiLog]:
    """8.1/8.2-band: vazifa yakunlanganda chaqiriladi. Muddatidan kech tugagan bo'lsa,
    `apply_penalty_for_employees()` orqali vazifaga biriktirilgan xodim(lar)ga
    jarima yozadi (brigadir ulushi bilan birga). Muddatida yoki muddatidan
    oldin tugagan bo'lsa — bo'sh ro'yxat qaytaradi, hech narsa yozilmaydi
    (8.1: jarima FAQAT muddatni buzganga nisbatan).

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
        if task.finished_at <= reference_start:
            return []

        hours_late = int((task.finished_at - reference_start).total_seconds() // 3600)
        department_id = task.current_department_id
        employee_ids = [a.employee_id for a in await assignment_repo.list_by_task(task_id)]

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


def calculate_plus_ball(task_id: int) -> int:
    """8.4-band: plus ball mezonlari hali tasdiqlanmagan (19-band ochiq savol).
    Mezon kelishilgach shu funksiya to'ldiriladi; hozircha stub."""
    return 0


async def apply_brigade_share(worker_score: int, ratio: float | None = None) -> float:
    """8.4-band: ishchining minus balidan brigadirga o'tadigan ulushni hisoblaydi
    (faqat arifmetika — kimning brigadiri ekanini aniqlamaydi, chaqiruvchi
    aniqlaydi). `ratio` berilmasa, `settings_service`dagi joriy
    `brigade_share_ratio` ishlatiladi (admin `/settings` orqali o'zgartirgan)."""
    if ratio is None:
        ratio = (await settings_service.get_settings()).brigade_share_ratio
    return worker_score * ratio
