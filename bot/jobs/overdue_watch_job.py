"""Soatlik muddat-kuzatuv job'i (7.2-band: "1 kun qoldi" / "muddat o'tdi"
hodisalari; 8.3-band: uzoq kechikkan buyurtmani boshqa brigadaga o'tkazish
signali). `core/scheduler.py` orqali har soat boshida (`minute=0`) ishga
tushiriladi (`main.py`da ro'yxatdan o'tkaziladi).

Har uch qism ham mustaqil — bittasidagi xatolik qolganlarini to'xtatmaydi.
Har biri "signal faqat bir marta" ustunini (`day_left_notified_at`,
`status=OVERDUE` o'zi, `reassignment_signaled_at`) yozgach qayta ishga
tushganda takrorlanmaydi.
"""

import logging
from datetime import datetime, timezone

from aiogram import Bot

from core.database import async_session
from db.repositories import TaskRepository
from services import financial_service, notification_service, settings_service
from utils.enums import TaskStatus

logger = logging.getLogger(__name__)


async def _process_deadline_approaching(bot: Bot, now: datetime) -> int:
    async with async_session() as session:
        task_repo = TaskRepository(session)
        tasks = await task_repo.list_deadline_approaching(now=now)
        task_ids = []
        for task in tasks:
            await task_repo.update(task, day_left_notified_at=now)
            task_ids.append(task.id)
        await session.commit()

    for task_id in task_ids:
        try:
            await notification_service.notify_deadline_approaching(bot, task_id)
        except Exception:
            logger.exception("overdue_watch_job: notify_deadline_approaching xatosi (task_id=%s)", task_id)

    return len(task_ids)


async def _process_newly_overdue(bot: Bot, now: datetime) -> int:
    async with async_session() as session:
        task_repo = TaskRepository(session)
        tasks = await task_repo.list_newly_overdue(now=now)
        task_ids = []
        for task in tasks:
            await task_repo.update(task, status=TaskStatus.OVERDUE)
            task_ids.append(task.id)
        await session.commit()

    for task_id in task_ids:
        try:
            await notification_service.notify_task_overdue(bot, task_id)
        except Exception:
            logger.exception("overdue_watch_job: notify_task_overdue xatosi (task_id=%s)", task_id)

    return len(task_ids)


async def _process_reassignment_signals(bot: Bot, now: datetime) -> int:
    """8.3-band: faqat AVTOMATIK aniqlash+signal — brigadani o'zi tanlab
    almashtirish qo'lda (`handlers/admin/reassign_task.py`)."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        tasks = await task_repo.list_overdue_for_reassignment_check(now=now)
        task_ids = []
        for task in tasks:
            await task_repo.update(task, reassignment_signaled_at=now)
            task_ids.append(task.id)
        await session.commit()

    for task_id in task_ids:
        try:
            await notification_service.notify_reassignment_candidate(bot, task_id)
        except Exception:
            logger.exception(
                "overdue_watch_job: notify_reassignment_candidate xatosi (task_id=%s)", task_id
            )

    return len(task_ids)


async def _process_financial_flags(bot: Bot, now: datetime) -> int:
    """8.6-band 1-qoida: bosqich sozlangan `financial_flag_threshold_days`dan
    ortiq davom etsa, moliyaviy taklif (summa hali noma'lum holatda)
    avtomatik yaratiladi — admin keyinroq summani kelajakdagi UI orqali
    to'ldiradi. Idempotentlik `FinancialSuggestionRepository.exists_for_task`
    orqali (`financial_service.flag_long_duration_stage` ichida)."""
    threshold_days = (await settings_service.get_settings()).financial_flag_threshold_days
    async with async_session() as session:
        candidates = await TaskRepository(session).list_long_running_stages(
            threshold_days=threshold_days, now=now
        )
        task_ids = [t.id for t in candidates]

    suggestion_ids = []
    for task_id in task_ids:
        try:
            suggestion = await financial_service.flag_long_duration_stage(task_id)
        except Exception:
            logger.exception("overdue_watch_job: flag_long_duration_stage xatosi (task_id=%s)", task_id)
            continue
        if suggestion is not None:
            suggestion_ids.append(suggestion.id)

    for suggestion_id in suggestion_ids:
        try:
            await notification_service.notify_financial_flag(bot, suggestion_id)
        except Exception:
            logger.exception(
                "overdue_watch_job: notify_financial_flag xatosi (suggestion_id=%s)", suggestion_id
            )

    return len(suggestion_ids)


async def run(bot: Bot) -> None:
    now = datetime.now(timezone.utc)

    try:
        approaching = await _process_deadline_approaching(bot, now)
    except Exception:
        logger.exception("overdue_watch_job: deadline-approaching bosqichida xatolik")
        approaching = 0

    try:
        overdue = await _process_newly_overdue(bot, now)
    except Exception:
        logger.exception("overdue_watch_job: newly-overdue bosqichida xatolik")
        overdue = 0

    try:
        reassignment = await _process_reassignment_signals(bot, now)
    except Exception:
        logger.exception("overdue_watch_job: reassignment-signal bosqichida xatolik")
        reassignment = 0

    try:
        financial_flags = await _process_financial_flags(bot, now)
    except Exception:
        logger.exception("overdue_watch_job: moliyaviy bayroqlash bosqichida xatolik")
        financial_flags = 0

    logger.info(
        "overdue_watch_job yakunlandi: %s ta '1 kun qoldi', %s ta yangi OVERDUE, "
        "%s ta reassignment signali, %s ta moliyaviy bayroq",
        approaching, overdue, reassignment, financial_flags,
    )
