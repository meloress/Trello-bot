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

from core.database import async_session
from db.repositories import EmployeeRepository, StopLogRepository, TaskAssignmentRepository, TaskRepository
from services import penalty_service, timer_service
from utils.enums import TaskStatus, TaskType

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


def _own_lists(full_name: str, before: str, after: str) -> bool:
    """Ikkala list nomida ham shu odamning ismi bor ("Abdulloh kroy chizish")."""
    before, after = (before or "").lower(), (after or "").lower()
    return any(len(t) >= 4 and t in before and t in after for t in (full_name or "").lower().split())


def plan_list_move(before: str, after: str, holds) -> dict:
    """Karta `before` listdan `after`ga o'tdi — har bir ochiq hold bilan nima
    qilinadi. holds: [(task_id, full_name)]. Qaytaradi: {task_id: PAUSE|RESUME|KEEP|CLOSE}."""
    plan = {}
    for task_id, full_name in holds:
        if is_stop_list(after):
            plan[task_id] = KEEP if is_stop_list(before) else PAUSE
        elif is_stop_list(before):
            plan[task_id] = RESUME
        elif (is_date_list(before) and is_date_list(after)) or _own_lists(full_name, before, after):
            plan[task_id] = KEEP
        else:
            plan[task_id] = CLOSE
    return plan


def effective_deadline(due, started_at, stopped_seconds: int = 0):
    """Hold baholanadigan muddat: karta muddati + pauzada turgan vaqt.
    Odamga berilganda muddat allaqachon o'tib ketgan bo'lsa — muddat yo'q."""
    if due is None or due <= started_at:
        return None
    return due + timedelta(seconds=stopped_seconds or 0)


async def open_holds(card_id: str) -> list[tuple[int, int, datetime]]:
    async with async_session() as session:
        tasks = await TaskRepository(session).list_open_by_trello_card_id(card_id)
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


async def set_card_deadline(card_id: str, deadline) -> None:
    """Nazoratchi Trello'da muddatni o'zgartirdi — ochiq holdlar ham yangilanadi
    ("muddat yaqin"/"muddat o'tdi" eslatmalari yangi muddatga qarab qayta ishlasin)."""
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        repo = TaskRepository(session)
        for task in await repo.list_open_by_trello_card_id(card_id):
            effective = effective_deadline(deadline, task.started_at, task.stopped_seconds_total)
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
        changes = {"status": TaskStatus.ACTIVE, "stopped_seconds_total": (task.stopped_seconds_total or 0) + paused}
        if task.deadline is not None:
            changes["deadline"] = task.deadline + timedelta(seconds=paused)
        await repo.update(task, **changes)
        await session.commit()
    logger.info("trello hold davom etdi: task=%s (pauza %s soniya)", task_id, paused)


async def card_moved(bot, card_id: str, *, before: str, after: str, at: datetime, due) -> None:
    holds = await open_holds(card_id)
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        names = []
        for task_id, employee_id, _ in holds:
            employee = await employee_repo.get_by_id(employee_id)
            names.append((task_id, employee.full_name if employee else ""))
    started = {task_id: started_at for task_id, _, started_at in holds}
    for task_id, action in plan_list_move(before, after, names).items():
        if action == PAUSE:
            await pause_hold(task_id, at=at)
        elif action == RESUME:
            await resume_hold(task_id, at=at)
        elif action == CLOSE:
            await close_hold(bot, task_id, at=at, due=due, started_at=started[task_id])


async def close_hold(bot, task_id: int, *, at: datetime, due, started_at: datetime) -> None:
    """Holdni yopadi va (kerak bo'lsa) eski tizim bo'yicha ball yozadi."""
    await resume_hold(task_id, at=at)  # pauzada yopilsa — pauza vaqti muddatga qo'shilsin
    found, deadline = await _store_deadline(task_id, due)
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


async def _store_deadline(task_id: int, due) -> tuple[bool, datetime | None]:
    """Yopilish paytidagi karta muddatini (pauza bilan) yozadi.
    (False, None) — hold allaqachon yopilgan."""
    async with async_session() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if task is None or task.status == TaskStatus.COMPLETED:
            return False, None
        deadline = effective_deadline(due, task.started_at, task.stopped_seconds_total)
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

    # muddat odamga berilishidan oldin o'tib ketgan bo'lsa — muddat yo'q
    assert effective_deadline(t0 - timedelta(days=3), t0) is None
    assert effective_deadline(t0, t0) is None
    assert effective_deadline(t0 + timedelta(days=1), t0, 3600) == t0 + timedelta(days=1, hours=1)
    print("trello_hold_service: OK")


if __name__ == "__main__":
    demo()
