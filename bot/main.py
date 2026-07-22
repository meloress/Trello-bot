import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo

from config import settings
from core.logger import setup_logging
from core.scheduler import scheduler
from handlers.common.client_link import router as common_client_link_router
from handlers.common.start import router as common_start_router
from jobs import daily_sync_job, lead_follow_up_job, overdue_watch_job, reminder_job, report_job
from miniapp.server import run as run_miniapp_server
from services import settings_service


async def main() -> None:
    setup_logging()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    # Chat endi FAQAT `/start` (ro'yxatdan o'tish + Mini App tugmasi) va
    # `/mijoz`ni (mijozlar Mini App'ga kira olmaydi) qo'llab-quvvatlaydi —
    # barcha rol uchun qolgan HAMMA funksiya Mini App ichida (`bot/miniapp/`).
    dp.include_router(common_start_router)
    dp.include_router(common_client_link_router)

    # Mini App bo'lim tugmasi: faqat MINIAPP_BASE_URL sozlangan bo'lsa (masalan
    # Railway'da public domain yoqilgach) — lokal ishlab chiqishda bu qadam
    # jim o'tkazib yuboriladi, chat funksiyalariga ta'sir qilmaydi.
    if settings.miniapp_base_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Ilova", web_app=WebAppInfo(url=settings.miniapp_base_url)
            )
        )

    # app_settings'ni oldindan keshlab olamiz -- reminder_job/report_job
    # schedule_all() shu yerdan mos sozlamani oladi; admin /reminders yoki
    # /settings (report_time) orqali o'zgartirsa, handler o'sha funksiyani
    # qayta chaqirib job'larni yangilaydi.
    app_settings = await settings_service.get_settings()
    reminder_job.schedule_all(bot, app_settings.reminder_schedule)
    report_job.schedule_all(bot, app_settings.report_time)

    scheduler.add_job(
        daily_sync_job.run, "cron", hour=1, minute=0, args=[bot], id="daily_sync_job"
    )
    scheduler.add_job(
        overdue_watch_job.run, "cron", minute=0, args=[bot], id="overdue_watch_job"
    )
    scheduler.add_job(
        lead_follow_up_job.run, "cron", hour=10, minute=0, args=[bot], id="lead_follow_up_job"
    )

    scheduler.start()
    try:
        await asyncio.gather(
            dp.start_polling(bot),
            run_miniapp_server(bot, settings.port),
        )
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
