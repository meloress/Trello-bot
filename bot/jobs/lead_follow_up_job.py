"""13.3-band: kunlik job — uzoq vaqt aloqaga chiqilmagan (ochiq) lidlarni
topib, mas'ul sotuvchiga eslatma yuboradi. `core/scheduler.py` orqali
`main.py`da kunlik ro'yxatdan o'tkaziladi."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from core.database import async_session
from db.repositories import LeadRepository
from services import notification_service, settings_service

logger = logging.getLogger(__name__)


async def run(bot: Bot) -> None:
    threshold_days = (await settings_service.get_settings()).lead_follow_up_threshold_days
    threshold = datetime.now(timezone.utc) - timedelta(days=threshold_days)

    async with async_session() as session:
        leads = await LeadRepository(session).list_stale_open(threshold)
        lead_ids = [lead.id for lead in leads]

    for lead_id in lead_ids:
        try:
            await notification_service.notify_lead_follow_up(bot, lead_id)
        except Exception:
            logger.exception("lead_follow_up_job: notify_lead_follow_up xatosi (lead_id=%s)", lead_id)

    logger.info("lead_follow_up_job yakunlandi: %s ta eslatma", len(lead_ids))
