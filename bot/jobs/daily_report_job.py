"""Kunlik rasm/video hisobot SO'ROVI (Fasad sex TZ, Phase 8): har kuni
`app_settings.daily_report_time`da (Toshkent) `daily_report_required=True`
FAOL xodimlarga oddiy so'rov xabari yuboriladi. `reminder_job.py`/
`report_job.py` bilan bir xil naqsh: `schedule_all()` eski
`daily_report_job_*` job(lar)ini olib tashlab qayta yaratadi — `main.py`da
ishga tushishda va `daily_report_time` o'zgarganda (`miniapp/api/admin.py`)
qayta chaqiriladi."""

import logging

from aiogram import Bot

from core.database import async_session
from core.scheduler import scheduler
from db.repositories import EmployeeRepository
from services import notification_service

logger = logging.getLogger(__name__)

_JOB_PREFIX = "daily_report_job_"


async def run(bot: Bot) -> None:
    try:
        async with async_session() as session:
            employees = await EmployeeRepository(session).list_daily_report_required()
    except Exception:
        logger.exception("daily_report_job: xodimlarni yig'ishda xatolik")
        return

    if not employees:
        logger.info("daily_report_job: kunlik hisobot ro'yxatida xodim yo'q")
        return

    sent = 0
    failed = 0
    for employee in employees:
        try:
            ok = await notification_service.notify_daily_report_request(bot, employee.id)
            sent += int(ok)
            failed += int(not ok)
        except Exception:
            logger.exception("daily_report_job: xodim %s uchun so'rov yuborishda xatolik", employee.id)
            failed += 1

    logger.info("daily_report_job yakunlandi: %s xodimga yuborildi, %s xodimga yetmadi", sent, failed)


def schedule_all(bot: Bot, daily_report_time: str) -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith(_JOB_PREFIX):
            job.remove()

    hour, minute = (int(part) for part in daily_report_time.split(":"))
    scheduler.add_job(
        run, "cron", hour=hour, minute=minute, args=[bot], id=f"{_JOB_PREFIX}main"
    )
