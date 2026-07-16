import asyncio

from aiogram import Bot, Dispatcher

from config import settings
from core.logger import setup_logging
from core.scheduler import scheduler
from handlers.admin.advance_task import router as admin_advance_task_router
from handlers.admin.employee_management import router as admin_employee_management_router
from handlers.admin.misc_tasks import router as admin_misc_tasks_router
from handlers.admin.settings import router as admin_settings_router
from handlers.admin.stats import router as admin_stats_router
from handlers.admin.task_create import router as admin_task_create_router
from handlers.brigadier.stats import router as brigadier_stats_router
from handlers.common.start import router as common_start_router
from handlers.worker.tasks import router as worker_tasks_router
from jobs import daily_sync_job, reminder_job
from services import settings_service


async def main() -> None:
    setup_logging()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp.include_router(common_start_router)
    dp.include_router(admin_employee_management_router)
    dp.include_router(admin_task_create_router)
    dp.include_router(admin_misc_tasks_router)
    dp.include_router(admin_advance_task_router)
    dp.include_router(admin_settings_router)
    dp.include_router(admin_stats_router)
    dp.include_router(brigadier_stats_router)
    dp.include_router(worker_tasks_router)
    # TODO: handlers/ ichidagi qolgan routerlarni (sales) shu yerga qo'shish

    # app_settings'ni oldindan keshlab olamiz -- reminder_job shu yerdan
    # remind_time'ni oladi, admin /settings orqali o'zgartirsa
    # scheduler.reschedule_job() bilan qayta rejalashtiriladi.
    app_settings = await settings_service.get_settings()

    scheduler.add_job(
        reminder_job.run,
        "cron",
        hour=app_settings.remind_time.hour,
        minute=app_settings.remind_time.minute,
        args=[bot],
        id="reminder_job",
    )
    scheduler.add_job(
        daily_sync_job.run, "cron", hour=1, minute=0, args=[bot], id="daily_sync_job"
    )

    scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
