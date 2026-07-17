"""Davriy Telegram hisobotlari (10.2-band): kunlik/haftalik/oylik qisqa
statistika, ADMIN va SUPERVISOR'larga. `/stats` (handlers/admin/stats.py)
FAQAT so'rov bo'yicha ishlaydi — bu job'lar shu yerga qo'shimcha, o'zi
avtomatik yuboriladi. Vaqti `app_settings.report_time` (16-band, sozlanuvchan)
— `reminder_job.schedule_all()` bilan bir xil naqsh: `schedule_all()` eski
`report_job_*` job'larini olib tashlab qayta yaratadi, `handlers/admin/
settings.py` `report_time` o'zgarganda shu funksiyani qayta chaqiradi.

Kun/hafta/oy TANLOVI (yakshanba, har oyning 1-sanasi) sozlanuvchan emas —
TZda faqat "kunlik/haftalik/oylik" so'ralgan, aniq kun so'ralmagan."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from core.scheduler import scheduler
from services import notification_service, stats_service

logger = logging.getLogger(__name__)

_JOB_PREFIX = "report_job_"


async def run_daily(bot: Bot) -> None:
    try:
        stats = await stats_service.get_daily_stats()
        text = stats_service.format_stats_table(stats, "📅 Kunlik hisobot")
        await notification_service.notify_admins_report(bot, text)
    except Exception:
        logger.exception("report_job: kunlik hisobot xatosi")


async def run_weekly(bot: Bot) -> None:
    try:
        stats = await stats_service.get_weekly_stats()
        text = stats_service.format_stats_table(stats, "🗓 Haftalik hisobot")
        await notification_service.notify_admins_report(bot, text)
    except Exception:
        logger.exception("report_job: haftalik hisobot xatosi")


async def run_monthly(bot: Bot) -> None:
    """Har oyning 1-sanasida ishga tushadi — shu sabab O'TGAN oy uchun
    (`reference_month` joriy kunning bir kun oldingisi, hali yangi oy
    boshlanmaganidek hisoblanadi)."""
    try:
        previous_month_reference = datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
        stats = await stats_service.get_monthly_stats(previous_month_reference)
        text = stats_service.format_stats_table(stats, "📊 Oylik hisobot")
        await notification_service.notify_admins_report(bot, text)
    except Exception:
        logger.exception("report_job: oylik hisobot xatosi")


def schedule_all(bot: Bot, report_time: str) -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith(_JOB_PREFIX):
            job.remove()

    hour, minute = (int(part) for part in report_time.split(":"))
    scheduler.add_job(run_daily, "cron", hour=hour, minute=minute, args=[bot], id=f"{_JOB_PREFIX}daily")
    scheduler.add_job(
        run_weekly, "cron", day_of_week="sun", hour=hour, minute=minute, args=[bot], id=f"{_JOB_PREFIX}weekly"
    )
    scheduler.add_job(
        run_monthly, "cron", day=1, hour=hour, minute=minute, args=[bot], id=f"{_JOB_PREFIX}monthly"
    )
