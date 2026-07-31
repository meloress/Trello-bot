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
from db.models.stop_log import StopLog
from db.models.task import Task
from db.models.task_assignment import TaskAssignment
from services import settings_service
from utils.enums import Role, TaskStatus, TaskType

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
    # SPEC.md §11: "har bir xodim: ... o'rtacha bajarish vaqti". Soatda,
    # STOP vaqti CHIQARIB TASHLANGAN (§6) — `stopped_seconds_total`.
    # `0.0` = shu davrda yakunlangan vazifa yo'q.
    avg_completion_hours: float


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

        # SPEC.md §11: o'rtacha bajarish vaqti — `completed_by_employee` bilan
        # BIR XIL filtr, faqat count o'rniga avg. Alohida so'rov, chunki
        # `count(distinct)` va `avg` bitta guruhlashda birga to'g'ri
        # ishlamaydi (bir vazifaga bir nechta tayinlov bo'lsa avg buziladi).
        worked_seconds = func.extract("epoch", Task.finished_at - Task.started_at) - func.coalesce(
            Task.stopped_seconds_total, 0
        )
        avg_hours_by_employee = dict(
            (
                await session.execute(
                    select(TaskAssignment.employee_id, func.avg(worked_seconds))
                    .join(Task, Task.id == TaskAssignment.task_id)
                    .where(
                        TaskAssignment.employee_id.in_(employee_ids),
                        Task.status == TaskStatus.COMPLETED,
                        Task.finished_at.isnot(None),
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
            avg_completion_hours=round(
                max(float(avg_hours_by_employee.get(employee_id) or 0), 0) / 3600, 1
            ),
        )
        for employee_id, full_name, role in employees
    ]


async def get_monthly_stats(
    reference_month: datetime | None = None,
    factory_name: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
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
    davom etadi.

    `since`/`until` — SPEC.md §11 "davr bo'yicha filtr": ixtiyoriy aniq
    oraliq. IKKALASI birga berilishi kerak; berilmasa (barcha mavjud
    chaqiruvchilar) avvalgidek `reference_month` oyi olinadi, ya'ni
    funksiya nomi ham, standart xatti-harakati ham o'zgarmaydi."""
    if since is None or until is None:
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


@dataclass(frozen=True)
class FunnelStage:
    """SPEC.md §11: "zakazlar voronkasi — qaysi bosqichda nechta zakaz turibdi"."""

    department_id: int
    department_name: str
    pending_setup: int
    active: int
    stopped: int
    overdue: int

    @property
    def total(self) -> int:
        return self.pending_setup + self.active + self.stopped + self.overdue


@dataclass(frozen=True)
class BottleneckStage:
    """SPEC.md §11: "har bir bosqich: o'rtacha davomiylik vs reja".

    `avg_hours` — STOP vaqti CHIQARIB TASHLANGAN sof ish vaqti (§6 oxirgi
    band: "aks holda ishchi 'men vaqtida qildim' deb bahslashadi").
    `planned_hours` — bo'limning `default_sla_hours`i; `None` bo'lsa reja
    belgilanmagan va taqqoslash ko'rsatilmaydi (nisbat hisoblanmaydi)."""

    department_id: int
    department_name: str
    completed_tasks: int
    avg_hours: float
    planned_hours: int | None


@dataclass(frozen=True)
class StopStats:
    """SPEC.md §11: "STOP statistikasi: nechta zakaz, qancha vaqt, sabablari"."""

    stop_count: int
    task_count: int
    total_hours: float
    reasons: list[tuple[str, int]]  # (sabab, nechta marta) — ko'pdan kamga


@dataclass(frozen=True)
class StoppedOrder:
    """SPEC.md §6: ""STOP bosilgan zakazlar" degan alohida ro'yxat/filtr
    bo'ladi" — hozir to'xtatilgan holatda turgan har bir buyurtma, sababi
    va qancha vaqtdan beri to'xtab turgani bilan."""

    task_id: int
    title: str
    department_name: str | None
    reason: str
    stopped_at: datetime
    stopped_hours: float


async def get_stopped_orders(module: str = "fasad_sex") -> list[StoppedOrder]:
    """SPEC.md §6: hozir STOP holatida turgan buyurtmalar — eng uzoq
    to'xtab turganidan boshlab. Har biri uchun faol `StopLog`dan sabab va
    boshlanish vaqti olinadi (faol stop yo'q bo'lsa qator o'tkazib
    yuboriladi — bunday holat `starts_stopped` oqimida bo'lmasligi kerak,
    lekin ma'lumot nomuvofiqligi butun ekranni yiqitmasin)."""
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        rows = (
            await session.execute(
                select(Task.id, Task.title, Department.name, StopLog.reason, StopLog.stopped_at)
                .join(Department, Task.current_department_id == Department.id)
                .join(StopLog, StopLog.task_id == Task.id)
                .where(
                    Department.module == module,
                    Task.status == TaskStatus.STOPPED,
                    StopLog.resumed_at.is_(None),
                )
            )
        ).all()

    return sorted(
        (
            StoppedOrder(
                task_id=task_id,
                title=title,
                department_name=department_name,
                reason=(reason or "").strip() or "—",
                stopped_at=stopped_at,
                stopped_hours=round(max((now - stopped_at).total_seconds(), 0) / 3600, 1),
            )
            for task_id, title, department_name, reason, stopped_at in rows
        ),
        key=lambda o: o.stopped_hours,
        reverse=True,
    )


async def get_order_funnel(module: str = "fasad_sex") -> list[FunnelStage]:
    """SPEC.md §11: har bo'limda hozir nechta OCHIQ buyurtma-bosqichi
    turganini holat kesimida qaytaradi (COMPLETED hisobga olinmaydi — bu
    "hozir qayerda turibdi" ko'rsatkichi, tarix emas).

    Bo'lim tartibi zanjir bo'ylab emas, nom bo'yicha — zanjir fork/join
    tufayli chiziqli emas, "birinchidan oxirigacha" degan yagona to'g'ri
    tartib mavjud emas."""
    open_statuses = (TaskStatus.PENDING_SETUP, TaskStatus.ACTIVE, TaskStatus.STOPPED, TaskStatus.OVERDUE)
    async with async_session() as session:
        rows = (
            await session.execute(
                select(Department.id, Department.name, Task.status, func.count(Task.id))
                .join(Task, Task.current_department_id == Department.id)
                .where(
                    Department.module == module,
                    Task.task_type == TaskType.ORDER,
                    Task.status.in_(open_statuses),
                )
                .group_by(Department.id, Department.name, Task.status)
            )
        ).all()

    by_department: dict[int, dict] = {}
    for department_id, name, status, count in rows:
        entry = by_department.setdefault(department_id, {"name": name})
        entry[status] = count

    return sorted(
        (
            FunnelStage(
                department_id=department_id,
                department_name=entry["name"],
                pending_setup=entry.get(TaskStatus.PENDING_SETUP, 0),
                active=entry.get(TaskStatus.ACTIVE, 0),
                stopped=entry.get(TaskStatus.STOPPED, 0),
                overdue=entry.get(TaskStatus.OVERDUE, 0),
            )
            for department_id, entry in by_department.items()
        ),
        key=lambda s: s.department_name,
    )


async def get_stage_bottlenecks(
    since: datetime, until: datetime, module: str = "fasad_sex"
) -> list[BottleneckStage]:
    """SPEC.md §11: bosqichlarning o'rtacha HAQIQIY davomiyligi vs reja
    (`default_sla_hours`) — eng sekinidan boshlab. Sekin bosqichni topish
    uchun ("bottleneck aniqlash").

    Davomiylik = `finished_at - started_at` MINUS `stopped_seconds_total`
    (§6: STOP vaqti ish vaqtidan chiqariladi). SQL darajasida hisoblanadi —
    bo'lim boshiga bitta qator qaytadi, vazifalar Python'ga tortilmaydi."""
    worked_seconds = func.extract("epoch", Task.finished_at - Task.started_at) - func.coalesce(
        Task.stopped_seconds_total, 0
    )
    async with async_session() as session:
        rows = (
            await session.execute(
                select(
                    Department.id,
                    Department.name,
                    Department.default_sla_hours,
                    func.count(Task.id),
                    func.avg(worked_seconds),
                )
                .join(Task, Task.current_department_id == Department.id)
                .where(
                    Department.module == module,
                    Task.task_type == TaskType.ORDER,
                    Task.status == TaskStatus.COMPLETED,
                    Task.finished_at.isnot(None),
                    Task.finished_at >= since,
                    Task.finished_at < until,
                )
                .group_by(Department.id, Department.name, Department.default_sla_hours)
            )
        ).all()

    return sorted(
        (
            BottleneckStage(
                department_id=department_id,
                department_name=name,
                completed_tasks=count,
                # Manfiy bo'lib qolishi mumkin emas, lekin soat noto'g'ri
                # yurgan/qo'lda tuzatilgan yozuvlarda 0'ga qisiladi.
                avg_hours=round(max(float(avg_seconds or 0), 0) / 3600, 1),
                planned_hours=planned,
            )
            for department_id, name, planned, count, avg_seconds in rows
        ),
        key=lambda s: s.avg_hours,
        reverse=True,
    )


async def get_stop_stats(since: datetime, until: datetime, module: str = "fasad_sex") -> StopStats:
    """SPEC.md §11: "STOP statistikasi: nechta zakaz, qancha vaqt, sabablari".

    Davr ichida BOSHLANGAN to'xtatishlar hisobga olinadi. Hali davom
    etayotgan STOP (`resumed_at IS NULL`) hisobdan tushib qolmaydi — uning
    davomiyligi HOZIRGACHA olinadi, `until`gacha emas: standart davr joriy
    oy, ya'ni `until` deyarli har doim KELAJAKDA, va o'sha kelajak vaqtni
    qo'shish "qancha vaqt to'xtab turildi" raqamini bir necha barobar
    shishirardi (haqiqiy DB'da 6 soat o'rniga 30 soat ko'rsatgan edi)."""
    cutoff = min(until, datetime.now(timezone.utc))
    async with async_session() as session:
        rows = (
            await session.execute(
                select(StopLog.task_id, StopLog.reason, StopLog.stopped_at, StopLog.resumed_at)
                .join(Task, StopLog.task_id == Task.id)
                .join(Department, Task.current_department_id == Department.id)
                .where(
                    Department.module == module,
                    StopLog.stopped_at >= since,
                    StopLog.stopped_at < until,
                )
            )
        ).all()

    total_seconds = 0.0
    reason_counts: dict[str, int] = {}
    task_ids = set()
    for task_id, reason, stopped_at, resumed_at in rows:
        task_ids.add(task_id)
        total_seconds += max(((resumed_at or cutoff) - stopped_at).total_seconds(), 0)
        key = (reason or "").strip() or "—"
        reason_counts[key] = reason_counts.get(key, 0) + 1

    return StopStats(
        stop_count=len(rows),
        task_count=len(task_ids),
        total_hours=round(total_seconds / 3600, 1),
        reasons=sorted(reason_counts.items(), key=lambda item: item[1], reverse=True),
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
