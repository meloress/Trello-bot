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
from db.models.department import Department
from db.models.employee import Employee
from db.models.kpi_log import KpiLog
from db.models.task import Task
from db.models.task_assignment import TaskAssignment
from services import settings_service
from utils.enums import Role, TaskStatus

# KPI/jarima faqat shu ikki operatsion rolga tegishli (penalty_service faqat
# WORKER'ni jarimalaydi, BRIGADIER esa brigade_share_ratio orqali ulush oladi) —
# admin/nazoratchi/sotuvchi/kuzatuvchida umuman ball bo'lmaydi. KPI reytingi/
# o'rtacha ball hisoblanadigan joylarda shu bilan filtrlanadi (lekin
# get_monthly_stats() o'zi filtrlamaydi — u "faol xodim" umumiy hisobi kabi
# KPI'ga aloqasiz narsalar uchun ham ishlatiladi, ular hamma rolni ko'rishi kerak).
KPI_ROLES = (Role.WORKER, Role.BRIGADIER)


@dataclass(frozen=True)
class EmployeeStats:
    employee_id: int
    full_name: str
    role: Role
    completed_tasks: int
    total_score: int
    penalty_count: int


@dataclass(frozen=True)
class CapacityStats:
    """Fasad sex TZ, Phase 6: kunlik norma (5 punkt/ishchi) ko'rsatkichi —
    FAQAT stats/dashboard uchun, jarima/timer emas (`penalty_service.py`ga
    umuman tegilmaydi). `actual_points` — bajarilgan vazifalar SONI, HAQIQIY
    kv.m/punkt o'lchovi EMAS (bunday ustun `tasks` jadvalida yo'q — ochiq
    savol #12, `.claude/plans/09z-fasad-sex-ochiq-savollar.md`). Ikkala
    maydon boshqa-boshqa birlikda — birini ikkinchisiga aylantirib, foiz/
    nisbat hisoblanmaydi (soxta aniqlik bo'lardi)."""

    worker_count: int
    planned_points: int
    actual_points: int


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


def _today_bounds(reference: datetime) -> tuple[datetime, datetime]:
    """[bugun 00:00, ertaga 00:00) — kunlik hisobot uchun (10.2-band)."""
    start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


async def _compute_stats(
    employees: list[tuple[int, str, Role]], since: datetime, until: datetime
) -> list[EmployeeStats]:
    """`employees` = (id, full_name, role) uchtaliklari ro'yxati — chaqiruvchi
    tomonidan oldindan filtrlangan (masalan bitta brigada a'zolari)."""
    if not employees:
        return []
    employee_ids = [employee_id for employee_id, _, _ in employees]

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
            role=role,
            completed_tasks=completed_by_employee.get(employee_id, 0),
            total_score=score_by_employee.get(employee_id, 0),
            penalty_count=penalty_count_by_employee.get(employee_id, 0),
        )
        for employee_id, full_name, role in employees
    ]


async def get_monthly_stats(
    reference_month: datetime | None = None, factory_name: str | None = None
) -> list[EmployeeStats]:
    """Barcha FAOL xodimlar uchun oy statistikasi (10-band, admin/stats/
    dashboard) — rol bo'yicha filtrlanmagan (dashboard'ning "faol xodim"
    umumiy hisobi ham shundan kelib chiqadi). KPI-ga xos ko'rinishlar (reyting,
    o'rtacha ball) chaqiruvchi tomonda `KPI_ROLES` bilan filtrlanadi.
    `reference_month` — shu oyning istalgan sanasi (Default: joriy oy);
    `jobs/report_job.py`ning oylik hisoboti O'TGAN oy uchun shu orqali chaqiradi.
    Faoliyati bo'sh xodim ham 0 qiymatlar bilan ro'yxatda bo'ladi.
    `factory_name` — Fasad sex TZ §9 "ikkinchi zavod": berilsa, faqat shu
    zavodga tegishli bo'limdagi (`Employee.department_id -> Department.
    factory_name`) xodimlar bilan cheklanadi. Default (`None`) — hech qanday
    filtr, `NULL` zavodli bo'limlar ham (barcha eski bo'limlar) natijada
    qoladi, xatti-harakat o'zgarishsiz — barcha mavjud chaqiruvchilar
    (masalan `jobs/report_job.py`) hech narsani o'zgartirmasdan ishlashda
    davom etadi."""
    since, until = _month_bounds(reference_month or datetime.now(timezone.utc))

    async with async_session() as session:
        query = select(Employee.id, Employee.full_name, Employee.role).where(Employee.is_active.is_(True))
        if factory_name is not None:
            query = query.join(Department, Department.id == Employee.department_id).where(
                Department.factory_name == factory_name
            )
        employees = (await session.execute(query)).all()

    return await _compute_stats(employees, since, until)


async def get_brigade_monthly_stats(brigade_id: int) -> list[EmployeeStats]:
    """11.1-band: brigadir oynasi — faqat shu brigadaga A'ZO (brigade_id)
    faol xodimlar bo'yicha joriy oy statistikasi."""
    since, until = _month_bounds(datetime.now(timezone.utc))

    async with async_session() as session:
        employees = (
            await session.execute(
                select(Employee.id, Employee.full_name, Employee.role).where(
                    Employee.brigade_id == brigade_id, Employee.is_active.is_(True)
                )
            )
        ).all()

    return await _compute_stats(employees, since, until)


async def get_daily_stats() -> list[EmployeeStats]:
    """10.2-band: `jobs/report_job.py`ning kunlik hisoboti — barcha FAOL
    xodimlar, bugungi kun (UTC kalendar kuni)."""
    since, until = _today_bounds(datetime.now(timezone.utc))

    async with async_session() as session:
        employees = (
            await session.execute(
                select(Employee.id, Employee.full_name, Employee.role).where(Employee.is_active.is_(True))
            )
        ).all()

    return await _compute_stats(employees, since, until)


async def get_weekly_stats() -> list[EmployeeStats]:
    """10.2-band: `jobs/report_job.py`ning haftalik hisoboti — barcha FAOL
    xodimlar, oxirgi 7 kun (11.1-band bitta-xodim variantidan farqli, bu
    yerda hammasi bitta jadvalda)."""
    since, until = _last_7_days_bounds(datetime.now(timezone.utc))

    async with async_session() as session:
        employees = (
            await session.execute(
                select(Employee.id, Employee.full_name, Employee.role).where(Employee.is_active.is_(True))
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
                select(Employee.id, Employee.full_name, Employee.role).where(Employee.id == employee_id)
            )
        ).first()

    if row is None:
        return None

    results = await _compute_stats([tuple(row)], since, until)
    return results[0] if results else None


async def get_capacity_vs_actual(department_id: int, since: datetime, until: datetime) -> CapacityStats:
    """Fasad sex TZ, Phase 6: kunlik norma (5 punkt/ishchi, xodim soniga
    proportsional) — VIZUAL ko'rsatkich, timer/jarima sifatida MAJBURIY
    QILINMAYDI (hozirgi shtat yetarli emasligini ko'rsatish uchun, jazolash
    uchun EMAS). `penalty_service.py`ga yoki muddat/timer logikasiga
    umuman tegilmaydi.

    `planned_points` = faol ISHCHI soni * `daily_quota_points_per_worker`
    * [since, until) oralig'idagi kunlar soni.

    `actual_points` — [since, until) oralig'ida shu bo'limda YAKUNLANGAN
    (`status=COMPLETED`, `current_department_id=department_id`) vazifalar
    SONI — bu HAQIQIY kv.m/punkt o'lchovi EMAS, faqat proksi (`tasks`
    jadvalida bunday ustun yo'q — ochiq savol #12,
    `.claude/plans/09z-fasad-sex-ochiq-savollar.md`). `planned_points` bilan
    BIR XIL BIRLIKDA EMAS — chaqiruvchi ikkalasini alohida raqam sifatida
    ko'rsatishi kerak, nisbat/foiz hisoblab soxta aniqlik yaratmasligi kerak.
    """
    quota = (await settings_service.get_settings()).daily_quota_points_per_worker
    days = max((until - since).days, 0)

    async with async_session() as session:
        worker_count = (
            await session.execute(
                select(func.count(Employee.id)).where(
                    Employee.department_id == department_id,
                    Employee.role == Role.WORKER,
                    Employee.is_active.is_(True),
                )
            )
        ).scalar_one()

        actual_points = (
            await session.execute(
                select(func.count(Task.id)).where(
                    Task.current_department_id == department_id,
                    Task.status == TaskStatus.COMPLETED,
                    Task.finished_at >= since,
                    Task.finished_at < until,
                )
            )
        ).scalar_one()

    return CapacityStats(
        worker_count=worker_count,
        planned_points=worker_count * quota * days,
        actual_points=actual_points,
    )


def format_stats_table(stats: list[EmployeeStats], title: str) -> str:
    """10-band: statistikani Telegram kod-blok jadvaliga formatlaydi — xodim
    ismidagi maxsus belgilar (_, *, `) Markdown parserini buzmasligi uchun
    (kod blok ichida Telegram hech narsani formatlab o'qimaydi, hammasi
    literal matn). `handlers/admin/stats.py` (on-demand) va
    `jobs/report_job.py` (scheduled) ikkalasi ham shu funksiyani ishlatadi."""
    if not stats:
        return f"{title}\n\nFaol xodimlar topilmadi."

    stats = sorted(stats, key=lambda s: s.total_score, reverse=True)

    name_width = max(len("Xodim"), max(len(s.full_name) for s in stats))
    header = f"{'Xodim'.ljust(name_width)} | Bajar. | Ball | Jarima"
    separator = "-" * len(header)

    lines = [f"{title} ({len(stats)} xodim)", "", header, separator]
    for s in stats:
        lines.append(
            f"{s.full_name.ljust(name_width)} | {str(s.completed_tasks).rjust(6)} | "
            f"{str(s.total_score).rjust(4)} | {str(s.penalty_count).rjust(6)}"
        )

    best = max(stats, key=lambda s: s.total_score)
    worst = max(stats, key=lambda s: s.penalty_count)

    lines.append("")
    if best.total_score > 0:
        lines.append(f"Eng yuqori ball: {best.full_name} ({best.total_score:+d})")
    if worst.penalty_count > 0:
        lines.append(f"Eng ko'p jarima (past unumdorlik): {worst.full_name} ({worst.penalty_count} marta)")

    return "```\n" + "\n".join(lines) + "\n```"
