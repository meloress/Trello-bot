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
  - karta arxivlanganda.
Yopilgan paytdagi KARTA muddati bilan solishtiriladi (nazoratchi muddatni
uzaytirgan bo'lsa — yangi muddat).

10 daqiqalik qoida (`HOLD_GRACE`): bir-biridan 10 daqiqa ichida qo'shilganlar
birga ishlaydi (bir-birini yopmaydi), va 10 daqiqadan kam ushlab turilgan
karta hisobga olinmaydi — aks holda ikki ishchini birdaniga qo'shish yoki
xato odamni darhol tuzatish birinchisiga "3 kun erta" bonusini berib yuborardi.
"""

import logging
from datetime import datetime, timedelta, timezone

from core.database import async_session
from db.repositories import TaskAssignmentRepository, TaskRepository
from services import penalty_service, timer_service
from utils.enums import TaskStatus, TaskType

logger = logging.getLogger(__name__)

# ponytail: bitta qat'iy qiymat; sozlama kerak bo'lsa app_settings'ga ko'chiriladi.
HOLD_GRACE = timedelta(minutes=10)

WORKER, OTHER, UNKNOWN = "worker", "other", "unknown"


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
            deadline=deadline,
            status=TaskStatus.ACTIVE,
            current_department_id=employee.department_id,
            started_at=started_at,
        )
        await TaskAssignmentRepository(session).create(task_id=task.id, employee_id=employee.id)
        await session.commit()
    logger.info("trello hold ochildi: task=%s karta=%s xodim=%s muddat=%s", task.id, card_id, employee.id, deadline)
    return task.id


async def set_card_deadline(card_id: str, deadline) -> None:
    """Nazoratchi Trello'da muddatni o'zgartirdi — ochiq holdlar ham yangilanadi
    ("muddat yaqin"/"muddat o'tdi" eslatmalari yangi muddatga qarab qayta ishlasin)."""
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        repo = TaskRepository(session)
        for task in await repo.list_open_by_trello_card_id(card_id):
            changes = {"deadline": deadline, "day_left_notified_at": None, "last_overdue_reminder_at": None}
            if task.status == TaskStatus.OVERDUE and deadline is not None and deadline > now:
                changes["status"] = TaskStatus.ACTIVE
            await repo.update(task, **changes)
        await session.commit()


async def close_hold(bot, task_id: int, *, at: datetime, deadline, started_at: datetime) -> None:
    """Holdni yopadi va (kerak bo'lsa) eski tizim bo'yicha ball yozadi."""
    if at - started_at < HOLD_GRACE or deadline is None:
        # 10 daqiqadan kam yoki muddatsiz karta — ball ham, bonus ham yo'q.
        try:
            await timer_service.finish_task(task_id, finished_at=at)
        except (timer_service.InvalidTaskStateError, timer_service.TaskNotFoundError):
            pass
        logger.info("trello hold ballsiz yopildi: task=%s (muddat=%s)", task_id, deadline)
        return

    if not await _store_deadline(task_id, deadline):
        return
    await penalty_service.finalize_task_and_apply_penalty(bot, task_id, finished_at=at)
    logger.info("trello hold yopildi va baholandi: task=%s", task_id)


async def _store_deadline(task_id: int, deadline) -> bool:
    """Yopilish paytidagi karta muddatini yozadi; hold allaqachon yopilgan bo'lsa False."""
    async with async_session() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if task is None or task.status == TaskStatus.COMPLETED:
            return False
        await repo.update(task, deadline=deadline)
        await session.commit()
    return True


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
    print("trello_hold_service: OK")


if __name__ == "__main__":
    demo()
