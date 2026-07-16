"""Statistika va Dashboard (10-band, 11.1-band): xodimlarning bajargan
vazifalari soni, jami KPI balli va jarimalar (kechikish) soni — turli
davr/guruh kesimlarida (barcha xodim/joriy oy — admin uchun; bitta
brigada/joriy oy — brigadir uchun; bitta xodim/oxirgi 7 kun — haftalik
hisobot uchun).

Asosiy printsip (10-band): ko'rsatkich xodim qo'lida qancha ish borligi EMAS —
har bir vazifa NECHA KUNDA bajarilgani (shundan kelib chiquvchi KPI). Uchta
metrika bitta GROUP BY so'rov bilan emas, uchta alohida guruhlangan so'rov
bilan olinadi (tasks/kpi_logs turli join yo'llariga ega), so'ng Python'da
employee_id bo'yicha birlashtiriladi — N+1 (xodim boshiga alohida so'rov)
o'rniga jami 4 ta so'rov yetarli. Guruh kichik bo'lsa (masalan bitta brigada),
so'rovlar `employee_id IN (...)` bilan cheklanadi — butun tizim bo'yicha
skanerlanmaydi.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from core.database import async_session
from db.models.employee import Employee
from db.models.kpi_log import KpiLog
from db.models.task import Task
from db.models.task_assignment import TaskAssignment
from utils.enums import TaskStatus


@dataclass(frozen=True)
class EmployeeStats:
    employee_id: int
    full_name: str
    completed_tasks: int
    total_score: int
    penalty_count: int


def _month_bounds(reference: datetime) -> tuple[datetime, datetime]:
    """[oy boshi 00:00, keyingi oy boshi 00:00) — yarim ochiq oraliq (UTC)."""
    start = datetime(reference.year, reference.month, 1, tzinfo=timezone.utc)
    if reference.month == 12:
        end = datetime(reference.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(reference.year, reference.month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _last_7_days_bounds(reference: datetime) -> tuple[datetime, datetime]:
    """[hozirdan 7 kun oldin, hozir) — "oxirgi 7 kunlik" (11.1-band)."""
    return reference - timedelta(days=7), reference


async def _compute_stats(
    employees: list[tuple[int, str]], since: datetime, until: datetime
) -> list[EmployeeStats]:
    """`employees` = (id, full_name) juftliklari ro'yxati — chaqiruvchi
    tomonidan oldindan filtrlangan (masalan bitta brigada a'zolari)."""
    if not employees:
        return []
    employee_ids = [employee_id for employee_id, _ in employees]

    async with async_session() as session:
        completed_by_employee = dict(
            (
                await session.execute(
                    select(TaskAssignment.employee_id, func.count(func.distinct(Task.id)))
                    .join(Task, Task.id == TaskAssignment.task_id)
                    .where(
                        TaskAssignment.employee_id.in_(employee_ids),
                        Task.status == TaskStatus.COMPLETED,
                        Task.finished_at >= since,
                        Task.finished_at < until,
                    )
                    .group_by(TaskAssignment.employee_id)
                )
            ).all()
        )

        score_by_employee = dict(
            (
                await session.execute(
                    select(KpiLog.employee_id, func.coalesce(func.sum(KpiLog.score), 0))
                    .where(
                        KpiLog.employee_id.in_(employee_ids),
                        KpiLog.created_at >= since,
                        KpiLog.created_at < until,
                    )
                    .group_by(KpiLog.employee_id)
                )
            ).all()
        )

        penalty_count_by_employee = dict(
            (
                await session.execute(
                    select(KpiLog.employee_id, func.count(KpiLog.id))
                    .where(
                        KpiLog.employee_id.in_(employee_ids),
                        KpiLog.created_at >= since,
                        KpiLog.created_at < until,
                        KpiLog.score < 0,
                    )
                    .group_by(KpiLog.employee_id)
                )
            ).all()
        )

    return [
        EmployeeStats(
            employee_id=employee_id,
            full_name=full_name,
            completed_tasks=completed_by_employee.get(employee_id, 0),
            total_score=score_by_employee.get(employee_id, 0),
            penalty_count=penalty_count_by_employee.get(employee_id, 0),
        )
        for employee_id, full_name in employees
    ]


async def get_monthly_stats() -> list[EmployeeStats]:
    """Barcha FAOL xodimlar uchun joriy oy statistikasi (10-band, admin/stats).
    Faoliyati bo'sh xodim ham 0 qiymatlar bilan ro'yxatda bo'ladi."""
    since, until = _month_bounds(datetime.now(timezone.utc))

    async with async_session() as session:
        employees = (
            await session.execute(
                select(Employee.id, Employee.full_name).where(Employee.is_active.is_(True))
            )
        ).all()

    return await _compute_stats(employees, since, until)


async def get_brigade_monthly_stats(brigade_id: int) -> list[EmployeeStats]:
    """11.1-band: brigadir oynasi — faqat shu brigadaga A'ZO (brigade_id)
    faol xodimlar bo'yicha joriy oy statistikasi."""
    since, until = _month_bounds(datetime.now(timezone.utc))

    async with async_session() as session:
        employees = (
            await session.execute(
                select(Employee.id, Employee.full_name).where(
                    Employee.brigade_id == brigade_id, Employee.is_active.is_(True)
                )
            )
        ).all()

    return await _compute_stats(employees, since, until)


async def get_employee_weekly_stats(employee_id: int) -> EmployeeStats | None:
    """11.1-band: bitta xodimning oxirgi 7 kunlik hisoboti. Xodim topilmasa
    None qaytaradi."""
    since, until = _last_7_days_bounds(datetime.now(timezone.utc))

    async with async_session() as session:
        row = (
            await session.execute(
                select(Employee.id, Employee.full_name).where(Employee.id == employee_id)
            )
        ).first()

    if row is None:
        return None

    results = await _compute_stats([tuple(row)], since, until)
    return results[0] if results else None
