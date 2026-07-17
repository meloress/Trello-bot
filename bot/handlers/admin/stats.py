"""Statistika va Dashboard (10-band): joriy oy bo'yicha xodimlar statistikasi.

Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR — RoleAccessMiddleware orqali,
modul darajasida routerga ulangan.
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from middlewares.auth import RoleAccessMiddleware
from services import stats_service
from utils.enums import Role

logger = logging.getLogger(__name__)

router = Router(name="admin_stats")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    try:
        stats = await stats_service.get_monthly_stats()
        text = stats_service.format_stats_table(stats, "Joriy oy statistikasi")
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        logger.exception("cmd_stats xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")
