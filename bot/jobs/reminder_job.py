"""Kunlik eslatma (7.3-band): bugun muddati tugaydigan faol vazifalar haqida
har bir xodimga alohida xabar, kun davomida bir necha marta eskalatsiya
darajasi (`ReminderUrgency`) bilan. `core/scheduler.py` orqali
`app_settings.reminder_schedule`dagi har bir vaqt uchun alohida cron job
sifatida ishga tushiriladi (`schedule_all()`, `main.py`da chaqiriladi).
"""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from core.database import async_session
from core.scheduler import scheduler
from db.models.task import Task
from db.repositories import TaskAssignmentRepository, TaskRepository
from services import notification_service
from utils.enums import ReminderUrgency, TaskStatus
from utils.formatters import TASHKENT_TZ

logger = logging.getLogger(__name__)

_JOB_PREFIX = "reminder_job_"


def _today_bounds_utc() -> tuple[datetime, datetime]:
    """Toshkent vaqti bo'yicha "bugun"ning [00:00, 24:00) oralig'ini UTC'da qaytaradi."""
    now_local = datetime.now(TASHKENT_TZ)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _collect_due_today() -> dict[int, list[Task]]:
    """employee_id -> bugun muddati tugaydigan vazifalari."""
    since, until = _today_bounds_utc()

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        tasks = await task_repo.list_due_between(
            since, until, [TaskStatus.ACTIVE, TaskStatus.STOPPED]
        )

        by_employee: dict[int, list[Task]] = {}
        for task in tasks:
            for assignment in await assignment_repo.list_by_task(task.id):
                by_employee.setdefault(assignment.employee_id, []).append(task)

        return by_employee


async def run(bot: Bot, urgency: ReminderUrgency) -> None:
    """Scheduler shu funksiyani `reminder_schedule`dagi har bir yozuv uchun
    chaqiradi. Xatolik butun jobni yiqitmaydi — faqat log qilinadi, keyingi
    rejalashtirilgan vaqt bo'yicha qayta ishga tushadi."""
    try:
        by_employee = await _collect_due_today()
    except Exception:
        logger.exception("reminder_job: vazifalarni yig'ishda xatolik")
        return

    if not by_employee:
        logger.info("reminder_job(%s): bugun muddati tugaydigan faol vazifa yo'q", urgency.value)
        return

    sent = 0
    failed = 0
    for employee_id, tasks in by_employee.items():
        try:
            ok = await notification_service.notify_daily_reminder(bot, employee_id, tasks, urgency)
            sent += int(ok)
            failed += int(not ok)
        except Exception:
            logger.exception("reminder_job: xodim %s uchun eslatma yuborishda xatolik", employee_id)
            failed += 1

    logger.info(
        "reminder_job(%s) yakunlandi: %s xodimga yuborildi, %s xodimga yetmadi (jami %s xodim, %s vazifa)",
        urgency.value, sent, failed, len(by_employee), sum(len(t) for t in by_employee.values()),
    )


def schedule_all(bot: Bot, schedule: list[dict]) -> None:
    """`app_settings.reminder_schedule`ga mos APScheduler cron job'larini
    ro'yxatdan o'tkazadi. Avval eski `reminder_job_*` job'larini olib
    tashlaydi — shu orqali ro'yxat qayta saqlanganda (qo'shish/tahrirlash/
    o'chirish) job'lar soni har doim ro'yxat bilan bir xil bo'lib qoladi
    (`handlers/admin/settings.py` shu funksiyani har o'zgarishdan keyin
    qayta chaqiradi)."""
    for job in scheduler.get_jobs():
        if job.id.startswith(_JOB_PREFIX):
            job.remove()

    for i, entry in enumerate(schedule):
        hour, minute = (int(part) for part in entry["time"].split(":"))
        scheduler.add_job(
            run,
            "cron",
            hour=hour,
            minute=minute,
            args=[bot, ReminderUrgency(entry["urgency"])],
            id=f"{_JOB_PREFIX}{i}",
        )
