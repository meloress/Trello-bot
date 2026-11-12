"""Nazorat Trello ball tizimi (2026-10-24, foydalanuvchi talabi): zakaz faqat
Trello'da beriladi va ball ham Trello'dagi harakatdan hisoblanadi.

Nazoratchi kartaga odam qo'shib muddat qo'yadi — o'sha paytdan odamning shu
kartadagi "ushlab turishi" (hold) boshlanadi. Hold bitta `tasks` qatori
(ORDER, `trello_card_id`, bitta `task_assignments`): shu tufayli ball ESKI
tizimning o'zidan yoziladi (`penalty_service.finalize_task_and_apply_penalty`
— kechikish jadvali, erta tugatsa bonus, xabarlar, Mini App Ball/Statistika,
20:00 hisoboti) — alohida ball mantiqi yo'q.

Hold qachon yopiladi (foydalanuvchi tanlovi):
  - kartaga YANGI odam qo'shilganda (eski odamni olib tashlash unutilsa ham);
  - odam kartadan olib tashlanganda;
  - karta arxivlanganda;
  - karta boshqa listga o'tkazilganda (2026-11-04) — `plan_list_move()`:
    nomida "stop" bo'lgan listga o'tsa — PAUZA (to'xtab turgan vaqt muddatga
    qo'shiladi), stopdan chiqsa — davom etadi; sanali listlar ("5 NOYABR")
    orasida va bitta odamning o'z listlari orasida ("Abdulloh jiyan chizish"
    -> "Abdulloh kroy chizish") ko'chirish hisobni to'xtatmaydi.
Yopilgan paytdagi KARTA muddati bilan solishtiriladi (nazoratchi muddatni
uzaytirgan bo'lsa — yangi muddat) + pauzada turgan vaqt.

Odamga berilgan paytda karta muddati ALLAQACHON o'tib ketgan bo'lsa, hold
muddatsiz hisoblanadi (unga bog'liq bo'lmagan kechikish yozilmaydi, "muddat
o'tdi" eslatmalari ham ketmaydi); nazoratchi yangi muddat qo'ysa — odatdagidek.

10 daqiqalik qoida (`HOLD_GRACE`): bir-biridan 10 daqiqa ichida qo'shilganlar
birga ishlaydi (bir-birini yopmaydi), va 10 daqiqadan kam ushlab turilgan
karta hisobga olinmaydi — aks holda ikki ishchini birdaniga qo'shish yoki
xato odamni darhol tuzatish birinchisiga "3 kun erta" bonusini berib yuborardi.

Pauza `timer_service.stop_task/resume_task` orqali EMAS: ular kartani Trello'da
stop listiga ko'chiradi va label qo'yadi — bot esa bu doskaga yozmaydi.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.database import async_session
from db.models.department import Department
from db.models.employee import Employee
from db.repositories import StopLogRepository, TaskAssignmentRepository, TaskRepository
from services import penalty_service, timer_service
from utils.enums import Role, TaskStatus, TaskType
from utils.modules import NAZORAT_TRELLO

logger = logging.getLogger(__name__)

# ponytail: bitta qat'iy qiymat; sozlama kerak bo'lsa app_settings'ga ko'chiriladi.
HOLD_GRACE = timedelta(minutes=10)

WORKER, OTHER, UNKNOWN = "worker", "other", "unknown"
PAUSE, RESUME, KEEP, CLOSE = "pause", "resume", "keep", "close"

_DATE_LIST = re.compile(
    r"^\s*\d{1,2}\s+(yanvar|fevral|mart|aprel|may|iyun|iyul|avgust|sentabr|sentyabr|oktabr|oktyabr|noyabr|dekabr)\b",
    re.IGNORECASE,
)


def plan_member_added(holds, employee_id, kind, at):
    """Kartaga a'zo qo'shildi — nima qilinadi.

    holds: [(task_id, employee_id, started_at)] — kartadagi ochiq holdlar.
    kind: WORKER (ball oladigan xodim), OTHER (sotuvchi/admin/nazoratchi —
    hech narsaga ta'sir qilmaydi), UNKNOWN (botga bog'lanmagan Trello a'zosi —
    "yangi odam" sifatida eskisini yopadi, lekin unga ball yozib bo'lmaydi).
    Qaytaradi: (yopiladigan task_id'lar, yangi hold ochilsinmi)."""
    if kind == OTHER:
        return [], False
    if employee_id is not None and any(emp == employee_id for _, emp, _ in holds):
        return [], False  # allaqachon shu kartada
    close = [task_id for task_id, emp, started in holds if at - started >= HOLD_GRACE]
    return close, kind == WORKER


def is_stop_list(name: str) -> bool:
    return "stop" in (name or "").lower()


def is_date_list(name: str) -> bool:
    return bool(_DATE_LIST.match(name or ""))


def _tokens(full_name: str) -> set[str]:
    return {t for t in (full_name or "").lower().split() if len(t) >= 4}


def ambiguous_tokens(full_names) -> frozenset:
    """Bir nechta xodimda uchraydigan ism qismlari ("abdulloh": Muruvatullayev
    Abdulloh va Abdulloh Qosimov) — list nomidan kimniki ekanini aniqlab bo'lmaydi."""
    seen, dup = set(), set()
    for name in full_names:
        for token in _tokens(name):
            (dup if token in seen else seen).add(token)
    return frozenset(dup)


def _own_lists(full_name: str, before: str, after: str, ambiguous=frozenset()) -> bool:
    """Ikkala list nomida ham shu odamning ismi bor ("Abdulloh kroy chizish").
    Boshqa xodimda ham bor ism hisobga olinmaydi — aks holda bir Abdullohdan
    ikkinchisiga o'tgan karta birinchisining hisobida qolib ketardi."""
    before, after = (before or "").lower(), (after or "").lower()
    return any(t in before and t in after for t in _tokens(full_name) - ambiguous)


def plan_list_move(before: str, after: str, holds, ambiguous=frozenset()) -> dict:
    """Karta `before` listdan `after`ga o'tdi — har bir ochiq hold bilan nima
    qilinadi. holds: [(task_id, full_name)]; ambiguous — `ambiguous_tokens()`.
    Qaytaradi: {task_id: PAUSE|RESUME|KEEP|CLOSE}."""
    plan = {}
    for task_id, full_name in holds:
        if is_stop_list(after):
            plan[task_id] = KEEP if is_stop_list(before) else PAUSE
        elif is_stop_list(before):
            plan[task_id] = RESUME
        elif (is_date_list(before) and is_date_list(after)) or _own_lists(full_name, before, after, ambiguous):
            plan[task_id] = KEEP
        else:
            plan[task_id] = CLOSE
    return plan


def status_after_resume(deadline, now) -> TaskStatus:
    """Pauzadan chiqqan hold holati. Muddat surilgandan keyin ham o'tgan bo'lsa
    (pauzadan oldin OVERDUE edi) — OVERDUE qoladi: ACTIVE qilinsa soatlik job
    uni qayta "yangi kechikkan" deb topib, "muddat o'tdi" xabarini takrorlardi."""
    return TaskStatus.OVERDUE if deadline is not None and deadline <= now else TaskStatus.ACTIVE


def effective_deadline(due, started_at, stopped_seconds: int = 0):
    """Hold baholanadigan muddat: karta muddati + pauzada turgan vaqt.
    Odamga berilganda muddat allaqachon o'tib ketgan bo'lsa — muddat yo'q."""
    if due is None or due <= started_at:
        return None
    return due + timedelta(seconds=stopped_seconds or 0)


def due_at(moment, due_changes, due_now):
    """Karta muddati `moment` paytida qanday edi. due_changes: Trello
    `updateCard:due` tarixi [(sana, eski_muddat)] o'sish tartibida."""
    for date, old_due in due_changes:
        if date > moment:
            return old_due
    return due_now


def closing_deadline(due, given_due, started_at, stopped_seconds):
    """Hold qaysi muddat bilan baholanadi. Odatda — kartaning hozirgi muddati.
    Muddat odamga berilganidan OLDINGI sanaga surilgan bo'lsa (2026-11-04,
    #202: 03.11 -> 30.10, foydalanuvchi qarori -1.04) — odamga BERILGAN
    PAYTDAGI muddat (`given_due`): ishchi kartani olmagan kunlar uchun jarima
    olmasin. Oraliqdagi o'zgarishlar hisobga olinmaydi (#203: 03.11 -> 29.11
    xato -> 29.10). Muddat olib tashlansa — muddatsiz."""
    if due is None:
        return None
    deadline = effective_deadline(due, started_at, stopped_seconds)
    if deadline is None:
        return effective_deadline(given_due, started_at, stopped_seconds)
    return deadline


def match_label(label_name: str | None, departments) -> Department | None:
    """Label nomida bo'limning `trello_label` so'zi bor ("MUBORAK" -> Raspil Muborak).
    Rang odamlar uchun, bot nomdan taniydi: bir xil rangli ikki label bo'lishi mumkin."""
    name = (label_name or "").lower()
    return next((d for d in departments if d.trello_label and d.trello_label.lower() in name), None)


def label_deadline(started_at: datetime, sla_hours: int | None, card_due):
    """Label holdi muddati: qo'yilgan payt + bo'lim SLA'si; SLA yo'q bo'lsa — karta muddati."""
    if sla_hours:
        return started_at + timedelta(hours=sla_hours)
    return effective_deadline(card_due, started_at)


async def label_departments() -> list[Department]:
    async with async_session() as session:
        return list((await session.scalars(select(Department).where(
            Department.module == NAZORAT_TRELLO, Department.trello_label.isnot(None)))).all())


async def _label_dept_ids(session) -> set[int]:
    return set(await session.scalars(select(Department.id).where(Department.trello_label.isnot(None))))


async def open_holds(card_id: str, *, label: bool = False) -> list[tuple[int, int, datetime]]:
    """Kartadagi ochiq holdlar. Label holdlari (raspil) a'zo/list/muddat
    hodisalariga bog'liq emas — ular faqat `label=True` bilan qaytadi."""
    async with async_session() as session:
        label_ids = await _label_dept_ids(session)
        tasks = [t for t in await TaskRepository(session).list_open_by_trello_card_id(card_id)
                 if (t.current_department_id in label_ids) == label]
        assignment_repo = TaskAssignmentRepository(session)
        holds = []
        for task in tasks:
            for assignment in await assignment_repo.list_by_task(task.id):
                holds.append((task.id, assignment.employee_id, task.started_at))
    return holds


async def open_hold(*, card_id: str, card_name: str, employee, started_at: datetime, deadline) -> int:
    async with async_session() as session:
        task = await TaskRepository(session).create(
            trello_card_id=card_id,
            task_type=TaskType.ORDER,
            title=card_name[:255],
            deadline=effective_deadline(deadline, started_at),
            status=TaskStatus.ACTIVE,
            current_department_id=employee.department_id,
            started_at=started_at,
        )
        await TaskAssignmentRepository(session).create(task_id=task.id, employee_id=employee.id)
        await session.commit()
    logger.info("trello hold ochildi: task=%s karta=%s xodim=%s muddat=%s", task.id, card_id, employee.id, task.deadline)
    return task.id


async def set_card_deadline(card_id: str, deadline, due_changes=()) -> None:
    """Nazoratchi Trello'da muddatni o'zgartirdi — ochiq holdlar ham yangilanadi
    ("muddat yaqin"/"muddat o'tdi" eslatmalari yangi muddatga qarab qayta ishlasin)."""
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        repo = TaskRepository(session)
        label_ids = await _label_dept_ids(session)  # raspil muddati karta muddatiga bog'liq emas
        for task in await repo.list_open_by_trello_card_id(card_id):
            if task.current_department_id in label_ids:
                continue
            given = due_at(task.started_at, due_changes, deadline)
            effective = closing_deadline(deadline, given, task.started_at, task.stopped_seconds_total)
            changes = {"deadline": effective, "day_left_notified_at": None, "last_overdue_reminder_at": None}
            if task.status == TaskStatus.OVERDUE and (effective is None or effective > now):
                changes["status"] = TaskStatus.ACTIVE
            await repo.update(task, **changes)
        await session.commit()


async def pause_hold(task_id: int, *, at: datetime) -> None:
    """Karta stop listiga o'tdi — hold to'xtaydi."""
    async with async_session() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if task is None or task.status not in (TaskStatus.ACTIVE, TaskStatus.OVERDUE):
            return
        assignments = await TaskAssignmentRepository(session).list_by_task(task_id)
        await repo.update(task, status=TaskStatus.STOPPED)
        await StopLogRepository(session).create(
            task_id=task_id,
            employee_id=assignments[0].employee_id,
            reason="Trello: karta stop listiga o'tkazildi",
            stopped_at=at,
        )
        await session.commit()
    logger.info("trello hold pauzada: task=%s", task_id)


async def resume_hold(task_id: int, *, at: datetime) -> None:
    """Pauzadagi hold davom etadi — to'xtab turgan vaqt muddatga qo'shiladi."""
    async with async_session() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if task is None or task.status != TaskStatus.STOPPED:
            return
        stop_repo = StopLogRepository(session)
        stop = await stop_repo.get_active_stop(task_id)
        paused = max(0, int((at - stop.stopped_at).total_seconds())) if stop else 0
        if stop:
            await stop_repo.update(stop, resumed_at=at)
        deadline = task.deadline + timedelta(seconds=paused) if task.deadline is not None else None
        await repo.update(
            task,
            status=status_after_resume(deadline, datetime.now(timezone.utc)),
            deadline=deadline,
            stopped_seconds_total=(task.stopped_seconds_total or 0) + paused,
        )
        await session.commit()
    logger.info("trello hold davom etdi: task=%s (pauza %s soniya)", task_id, paused)


async def _staff_names() -> dict[int, str]:
    """Nazorat Trello'ning faol ishchi/brigadirlari: {id: ism}."""
    async with async_session() as session:
        rows = (await session.execute(
            select(Employee.id, Employee.full_name)
            .join(Department, Employee.department_id == Department.id)
            .where(Department.module == NAZORAT_TRELLO, Employee.is_active,
                   Employee.role.in_([Role.WORKER, Role.BRIGADIER]))
        )).all()
    return {employee_id: name for employee_id, name in rows}


async def card_moved(bot, card_id: str, *, before: str, after: str, at: datetime, due, due_changes=()) -> None:
    holds = await open_holds(card_id)
    if not holds:
        return
    full_names = await _staff_names()
    names = [(task_id, full_names.get(employee_id, "")) for task_id, employee_id, _ in holds]
    started = {task_id: started_at for task_id, _, started_at in holds}
    plan = plan_list_move(before, after, names, ambiguous_tokens(full_names.values()))
    for task_id, action in plan.items():
        if action == PAUSE:
            await pause_hold(task_id, at=at)
        elif action == RESUME:
            await resume_hold(task_id, at=at)
        elif action == CLOSE:
            await close_hold(bot, task_id, at=at, due=due, started_at=started[task_id],
                             given_due=due_at(started[task_id], due_changes, due))


async def close_hold(bot, task_id: int, *, at: datetime, due, started_at: datetime, given_due=None) -> None:
    """Holdni yopadi va (kerak bo'lsa) eski tizim bo'yicha ball yozadi.
    given_due — odamga berilgan paytdagi karta muddati (`closing_deadline`)."""
    await resume_hold(task_id, at=at)  # pauzada yopilsa — pauza vaqti muddatga qo'shilsin
    found, deadline = await _store_deadline(task_id, due, given_due)
    if not found:
        return
    if at - started_at < HOLD_GRACE or deadline is None:
        # 10 daqiqadan kam yoki muddatsiz karta — ball ham, bonus ham yo'q.
        try:
            await timer_service.finish_task(task_id, finished_at=at)
        except (timer_service.InvalidTaskStateError, timer_service.TaskNotFoundError):
            pass
        logger.info("trello hold ballsiz yopildi: task=%s (muddat=%s)", task_id, deadline)
        return

    await penalty_service.finalize_task_and_apply_penalty(bot, task_id, finished_at=at)
    logger.info("trello hold yopildi va baholandi: task=%s", task_id)


async def open_label_hold(*, card_id: str, card_name: str, department: Department,
                          started_at: datetime, card_due) -> int | None:
    """Kartaga bo'lim labeli qo'yildi — bo'limning hamma faol ishchi/brigadiriga
    bitta hold (Trello a'zosi emas). Shu bo'limning ochiq holdi bo'lsa — None."""
    async with async_session() as session:
        repo = TaskRepository(session)
        if any(t.current_department_id == department.id for t in await repo.list_open_by_trello_card_id(card_id)):
            return None
        staff = list(await session.scalars(select(Employee.id).where(
            Employee.department_id == department.id, Employee.is_active,
            Employee.role.in_([Role.WORKER, Role.BRIGADIER]))))
        task = await repo.create(
            trello_card_id=card_id,
            task_type=TaskType.ORDER,
            title=card_name[:255],
            deadline=label_deadline(started_at, department.default_sla_hours, card_due),
            status=TaskStatus.ACTIVE,
            current_department_id=department.id,
            started_at=started_at,
        )
        assignment_repo = TaskAssignmentRepository(session)
        for employee_id in staff:
            await assignment_repo.create(task_id=task.id, employee_id=employee_id)
        await session.commit()
    logger.info("trello label holdi ochildi: task=%s karta=%s bo'lim=%s xodimlar=%s muddat=%s",
                task.id, card_id, department.id, staff, task.deadline)
    return task.id


async def close_label_holds(bot, card_id: str, *, at: datetime, department_id: int | None = None) -> None:
    """Label olindi (yoki karta arxivlandi) — label holdlari yopiladi va
    o'z muddati (qo'yilganda belgilangan) bilan baholanadi."""
    async with async_session() as session:
        label_ids = {department_id} if department_id is not None else await _label_dept_ids(session)
        tasks = [t for t in await TaskRepository(session).list_open_by_trello_card_id(card_id)
                 if t.current_department_id in label_ids]
    for task in tasks:
        if at - task.started_at < HOLD_GRACE or task.deadline is None:
            try:
                await timer_service.finish_task(task.id, finished_at=at)
            except (timer_service.InvalidTaskStateError, timer_service.TaskNotFoundError):
                pass
            logger.info("trello label holdi ballsiz yopildi: task=%s", task.id)
            continue
        await penalty_service.finalize_task_and_apply_penalty(bot, task.id, finished_at=at)
        logger.info("trello label holdi yopildi va baholandi: task=%s", task.id)


async def _store_deadline(task_id: int, due, given_due=None) -> tuple[bool, datetime | None]:
    """Yopilish paytidagi karta muddatini (pauza bilan) yozadi.
    (False, None) — hold allaqachon yopilgan."""
    async with async_session() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if task is None or task.status == TaskStatus.COMPLETED:
            return False, None
        deadline = closing_deadline(due, given_due, task.started_at, task.stopped_seconds_total)
        await repo.update(task, deadline=deadline)
        await session.commit()
    return True, deadline


def demo() -> None:
    t0 = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
    holds = [(1, 169, t0)]
    # 3 soatdan keyin boshqa ishchi qo'shildi -> eskisi yopiladi, yangisi ochiladi
    assert plan_member_added(holds, 170, WORKER, t0 + timedelta(hours=3)) == ([1], True)
    # 5 daqiqada ikkinchi ishchi -> birga ishlaydi, hech kim yopilmaydi
    assert plan_member_added(holds, 170, WORKER, t0 + timedelta(minutes=5)) == ([], True)
    # sotuvchi qo'shildi -> hech narsa
    assert plan_member_added(holds, 173, OTHER, t0 + timedelta(hours=3)) == ([], False)
    # botga bog'lanmagan odam -> eskisi yopiladi, unga hold ochilmaydi
    assert plan_member_added(holds, None, UNKNOWN, t0 + timedelta(hours=3)) == ([1], False)
    # o'sha odam qayta qo'shildi -> o'zgarish yo'q
    assert plan_member_added(holds, 169, WORKER, t0 + timedelta(hours=3)) == ([], False)

    # list ko'chirish (haqiqiy "nazorat trello" doskasidagi nomlar)
    h = [(1, "Muruvatullayev Abdulloh")]
    assert plan_list_move("Abdulloh kroy chizish 24 soat", "Fayl yeg'ish  va zapchast 24", h) == {1: CLOSE}
    assert plan_list_move("Abdulloh jiyan chizish 24 soat", "Abdulloh kroy chizish 24 soat", h) == {1: KEEP}
    assert plan_list_move("Abdulloh kroy chizish 24 soat", "zakaz tushti stopda", h) == {1: PAUSE}
    assert plan_list_move("zakaz tushti stopda", "Shkurkadan chiqqan zakazla (stopda rang tanlanmagan)", h) == {1: KEEP}
    assert plan_list_move("zakaz tushti stopda", "Abdulloh kroy chizish 24 soat", h) == {1: RESUME}
    assert plan_list_move("5 NOYABR", "12 noyabr", h) == {1: KEEP}
    assert plan_list_move("korpus sklad 24", "5 NOYABR", h) == {1: CLOSE}

    # bir xil ism ikki xodimda — list nomidan kimniki ekani noma'lum -> yopiladi
    amb = ambiguous_tokens(["Muruvatullayev Abdulloh", "Abdulloh Qosimov", "Ruziev Rinat"])
    assert amb == {"abdulloh"}
    assert plan_list_move("Abdulloh jiyan chizish 24", "Abdulloh kroy chizish 24", h, amb) == {1: CLOSE}
    assert plan_list_move("Muruvatullayev jiyan", "Muruvatullayev kroy", h, amb) == {1: KEEP}

    # pauzadan chiqish: muddat hali o'tgan bo'lsa OVERDUE qoladi
    assert status_after_resume(t0 - timedelta(hours=1), t0) == TaskStatus.OVERDUE
    assert status_after_resume(t0 + timedelta(hours=1), t0) == TaskStatus.ACTIVE
    assert status_after_resume(None, t0) == TaskStatus.ACTIVE

    # muddat odamga berilganidan oldingi sanaga surildi -> berilgan paytdagi muddat (#203 holati)
    given, typo, past = t0 + timedelta(days=1), t0 + timedelta(days=27), t0 - timedelta(days=4)
    changes = [(t0 - timedelta(minutes=1), None), (t0 + timedelta(days=1, hours=6), given),
               (t0 + timedelta(days=1, hours=7), typo)]
    assert due_at(t0, changes, past) == given and due_at(t0 + timedelta(days=2), changes, past) == past
    assert closing_deadline(past, due_at(t0, changes, past), t0, 0) == given  # 29.11 xatosi emas
    assert closing_deadline(t0 + timedelta(days=2), given, t0, 0) == t0 + timedelta(days=2)  # oddiy uzaytirish
    assert closing_deadline(None, given, t0, 0) is None  # muddat olib tashlandi
    assert closing_deadline(past, past, t0, 0) is None  # berilganda ham o'tgan edi -> ballsiz

    # muddat odamga berilishidan oldin o'tib ketgan bo'lsa — muddat yo'q
    assert effective_deadline(t0 - timedelta(days=3), t0) is None
    assert effective_deadline(t0, t0) is None
    assert effective_deadline(t0 + timedelta(days=1), t0, 3600) == t0 + timedelta(days=1, hours=1)
    # label (raspil): nomdan taniladi, katta-kichik harf farqisiz; muddat — SLA, bo'lmasa karta muddati
    raspil = Department(id=105, name="Raspil Muborak", trello_label="muborak")
    other = Department(id=1, name="Kroychi", trello_label=None)
    assert match_label("MUBORAK", [other, raspil]) is raspil
    assert match_label("Muborak raspil", [raspil]) is raspil
    assert match_label("SROK O'TGAN", [other, raspil]) is None and match_label(None, [raspil]) is None
    assert label_deadline(t0, 168, None) == t0 + timedelta(days=7)
    assert label_deadline(t0, None, t0 + timedelta(days=2)) == t0 + timedelta(days=2)
    assert label_deadline(t0, None, t0 - timedelta(days=1)) is None
    print("trello_hold_service: OK")


if __name__ == "__main__":
    demo()
