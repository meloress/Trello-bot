"""«Bitta zakazmi yoki ikkitami?» tugmalari (`jobs/order_topics_job._ask_twin`,
boshliq, 2026-11-24): bir mijozdan 48 soat ichida 2 zakaz kelsa admin/kuzatuvchi
tanlaydi; «Bitta» — ikkinchi zakaz birinchisining topiciga o'tadi."""

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from core.database import async_session
from db.repositories import EmployeeRepository
from jobs import order_topics_job

logger = logging.getLogger(__name__)

router = Router(name="common_order_merge")


@router.callback_query(F.data.startswith("twin:"))
async def on_twin(callback: CallbackQuery, bot: Bot) -> None:
    try:
        _, choice, new_thread, old_thread = callback.data.split(":")
        new_thread, old_thread = int(new_thread), int(old_thread)
    except ValueError:
        await callback.answer()
        return
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_telegram_id(callback.from_user.id)
    if employee is None or not employee.is_active or employee.role not in order_topics_job.TWIN_ROLES:
        await callback.answer("Bu tugma faqat admin va kuzatuvchi uchun", show_alert=True)
        return
    if choice == "1":
        merged = await order_topics_job.merge_topics(bot, new_thread, old_thread)
        note = "✅ Bitta zakaz — birlashtirildi" if merged else "ℹ️ Allaqachon birlashtirilgan"
    else:
        note = "➡️ Ikkita alohida zakaz qoldi"
    logger.info("order_merge: %s (%s) — %s %s->%s", employee.full_name, employee.id, choice, new_thread, old_thread)
    await callback.answer(note)
    try:
        await callback.message.edit_text(f"{callback.message.text}\n\n{note} ({employee.full_name})")
    except Exception:
        logger.exception("order_merge: xabar yangilanmadi")
