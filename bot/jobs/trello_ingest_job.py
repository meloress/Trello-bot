"""Mebel moduli: Trello -> bot bir tomonlama sinxronizatsiya (§3-4 TZ).

Har 5 daqiqada `module="mebel"` bo'limlarning Trello ro'yxatlarini o'qiydi
va bazani shunga moslaydi — bot hech qachon Trello'ga yozmaydi (bu jobning
o'zi ham hech qanday TrelloClient yozish metodini chaqirmaydi, faqat
`list_cards_in_list`/`get_card` orqali o'qiydi). Har bir karta mustaqil
qayta ishlanadi: bitta kartadagi xatolik qolganlarni to'xtatmaydi.

Har bir karta uchun to'rtta holat mumkin:
1. Arxivlangan (`closed=true`) -> buyurtma to'liq tugadi, `penalty_service.
   finalize_task_and_apply_penalty()` (`daily_sync_job`ning arxiv-yopish
   yo'li bilan bir xil, lekin bu safar 5 daqiqada, faqat mebel uchun).
2. Bazada BUTUNLAY yangi karta -> yangi buyurtma, `task_service.
   sync_trello_card_stage()`.
3. Bazadagi so'nggi qator COMPLETED, lekin karta boshqa bo'limga ko'chgan
   -> bosqich o'tishi (odatiy holat: claim tasdiqlangandan keyin odam
   kartani qo'lda ko'chirgan). Kutilmagan bo'limga ko'chgan bo'lsa (zanjir
   ketma-ketligiga mos kelmasa) -> avtomatik yaratilmaydi, faqat log.
4. Bazadagi so'nggi qator ochiq (COMPLETED emas):
   a. Bo'lim o'zgargan -> bosqich o'tishi, LEKIN eski qator hali
      "tasdiqlanmagan" holatda (ishchi claim hali tasdiqlanmagan yoki
      umuman yuborilmagan) -> `advanced_without_finish_claim_at` birinchi
      marta belgilanadi + bir martalik ogohlantirish, SHUNGA QARAMAY zanjir
      baribir davom etadi (jismoniy voqelik: karta allaqachon ko'chgan).
   b. Bo'lim bir xil -> steady-state: a'zolar/muddat o'zgarishini tekshiradi.

`core/scheduler.py` orqali har 5 daqiqada ishga tushiriladi (`main.py`da
ro'yxatdan o'tkaziladi).
"""

import logging
from datetime import datetime, timezone

from aiogram import Bot

from config import settings
from core.database import async_session
from db.repositories import DepartmentRepository, EmployeeRepository, TaskRepository
from services import notification_service, penalty_service, task_service, timer_service
from trello.client import TrelloClient
from utils.enums import TaskStatus

logger = logging.getLogger(__name__)


def _parse_due(card: dict) -> datetime | None:
    due_raw = card.get("due")
    if not due_raw:
        return None
    return datetime.fromisoformat(due_raw)


async def _handle_archived(bot: Bot, card_id: str) -> None:
    async with async_session() as session:
        latest = await TaskRepository(session).get_latest_by_trello_card_id(card_id)
    if latest is not None and latest.status != TaskStatus.COMPLETED:
        await penalty_service.finalize_task_and_apply_penalty(bot, latest.id, finished_at=None)


async def _handle_new_card(bot: Bot, department, card: dict) -> None:
    deadline = _parse_due(card)
    if deadline is None:
        logger.warning(
            "trello_ingest_job: karta %s uchun due sana yo'q, hali yaratilmaydi (bo'lim=%s)",
            card["id"], department.id,
        )
        return
    new_task = await task_service.sync_trello_card_stage(
        department_id=department.id,
        card_id=card["id"],
        title=card["name"],
        description=card.get("desc"),
        deadline=deadline,
        member_trello_ids=card.get("idMembers") or [],
        previous_task_id=None,
    )
    if new_task is not None:
        await notification_service.notify_task_started(bot, new_task.id)


async def _handle_stage_advance(bot: Bot, department, card: dict, previous_task_id: int, client_id: int | None) -> None:
    deadline = _parse_due(card)
    if deadline is None:
        logger.warning(
            "trello_ingest_job: karta %s uchun due sana yo'q, bosqich o'tkazilmaydi (bo'lim=%s)",
            card["id"], department.id,
        )
        return
    new_task = await task_service.sync_trello_card_stage(
        department_id=department.id,
        card_id=card["id"],
        title=card["name"],
        description=card.get("desc"),
        deadline=deadline,
        member_trello_ids=card.get("idMembers") or [],
        previous_task_id=previous_task_id,
        client_id=client_id,
    )
    if new_task is not None:
        await notification_service.notify_task_started(bot, new_task.id)


async def _handle_completed_reappeared(bot: Bot, department, card: dict, latest) -> None:
    """`latest.status == COMPLETED` va karta boshqa bo'limda ko'rinmoqda."""
    async with async_session() as session:
        old_department = (
            await DepartmentRepository(session).get_by_id(latest.current_department_id)
            if latest.current_department_id is not None else None
        )
    expected_next_id = old_department.next_department_id if old_department is not None else None
    if expected_next_id != department.id:
        logger.warning(
            "trello_ingest_job: karta %s kutilmagan bo'limga ko'chirilgan (oldingi bo'lim=%s, yangi=%s) — "
            "avtomatik bosqich yaratilmadi, qo'lda tekshiring",
            card["id"], latest.current_department_id, department.id,
        )
        return
    await _handle_stage_advance(bot, department, card, latest.id, latest.client_id)


async def _handle_open_task(bot: Bot, department, card: dict, latest) -> None:
    """`latest.status != COMPLETED` — vazifa hali ochiq, biror bo'limda davom etmoqda."""
    if latest.current_department_id != department.id:
        # Karta jismonan shu bo'limga ko'chirilgan, lekin eski bosqich hali
        # yopilmagan (ishchi claim'i tasdiqlanmagan yoki umuman yuborilmagan).
        # TZ qarori: zanjir baribir davom etadi, faqat bir martalik belgi+xabar.
        needs_notify = False
        async with async_session() as session:
            task_repo = TaskRepository(session)
            old_task = await task_repo.get_by_id(latest.id)
            if old_task is not None and old_task.advanced_without_finish_claim_at is None:
                await task_repo.update(old_task, advanced_without_finish_claim_at=datetime.now(timezone.utc))
                await session.commit()
                needs_notify = True
        if needs_notify:
            try:
                await notification_service.notify_reconciliation_needed(bot, latest.id)
            except Exception:
                logger.exception("trello_ingest_job: notify_reconciliation_needed xatosi (task_id=%s)", latest.id)

        await _handle_stage_advance(bot, department, card, latest.id, latest.client_id)
        return

    # Bir xil bo'lim — steady-state: a'zolar/muddat o'zgarishini tekshiramiz.
    member_ids = card.get("idMembers") or []
    deadline = _parse_due(card)

    reassign_to: int | None = None
    deadline_changed = False

    async with async_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(latest.id)
        if task is None:
            return

        last_seen_members = set(task.trello_last_seen_member_ids or [])
        if set(member_ids) != last_seen_members:
            added = [m for m in member_ids if m not in last_seen_members]
            employee_repo = EmployeeRepository(session)
            for trello_member_id in added:
                employee = await employee_repo.get_by_trello_member_id(trello_member_id)
                if employee is not None and employee.is_active:
                    reassign_to = employee.id
                    break

        if deadline is not None and task.deadline != deadline:
            await task_repo.update(task, deadline=deadline)
            deadline_changed = True

        await task_repo.update(
            task,
            trello_last_seen_list_id=card.get("idList"),
            trello_last_seen_member_ids=list(member_ids),
            trello_last_polled_at=datetime.now(timezone.utc),
        )
        await session.commit()

    if reassign_to is not None:
        await task_service.set_assignee_from_trello(latest.id, reassign_to)
    if deadline is not None and deadline_changed:
        await timer_service.reopen_if_overdue(latest.id, deadline)


async def _process_card(bot: Bot, department, card: dict) -> None:
    card_id = card["id"]

    if card.get("closed"):
        await _handle_archived(bot, card_id)
        return

    async with async_session() as session:
        latest = await TaskRepository(session).get_latest_by_trello_card_id(card_id)

    if latest is None:
        await _handle_new_card(bot, department, card)
        return

    if latest.status == TaskStatus.COMPLETED:
        if latest.current_department_id == department.id:
            return  # karta hali qo'lda ko'chirilmagan — kutish davom etadi
        await _handle_completed_reappeared(bot, department, card, latest)
        return

    await _handle_open_task(bot, department, card, latest)


async def run(bot: Bot) -> None:
    """Scheduler shu funksiyani chaqiradi. Bitta bo'lim/kartadagi xatolik
    qolganlarini tekshirishni to'xtatmaydi — har biri alohida try/except ichida."""
    async with async_session() as session:
        departments = await DepartmentRepository(session).list_by_module("mebel")
    departments = [d for d in departments if d.trello_list_id]

    processed = 0
    failed = 0

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for department in departments:
            try:
                cards = await trello.list_cards_in_list(department.trello_list_id)
            except Exception:
                logger.exception(
                    "trello_ingest_job: bo'lim %s (%s) kartalarini o'qishda xatolik",
                    department.id, department.trello_list_id,
                )
                failed += 1
                continue

            for card in cards:
                try:
                    await _process_card(bot, department, card)
                    processed += 1
                except Exception:
                    logger.exception(
                        "trello_ingest_job: karta %s (bo'lim %s) qayta ishlashda xatolik",
                        card.get("id"), department.id,
                    )
                    failed += 1

    logger.info(
        "trello_ingest_job yakunlandi: %s karta qayta ishlandi, %s xatolik (%s mebel bo'limi tekshirildi)",
        processed, failed, len(departments),
    )
