"""Ro'yxatdan o'tish va Mini App'ga yo'naltirish (5.2-band).

Bot endi barcha rol uchun to'liq Mini App'ga bog'langan — chatda /buyruq
yoki tugmali menyu yo'q, faqat `/start` (ro'yxatdan o'tish + ilova tugmasi)
va `/mijoz` (`handlers/common/client_link.py`, mijozlar uchun — ular xodim
emas, Mini App'ga kira olmaydi). Boshqa istalgan xabar shu modul oxiridagi
"hammasiga javob" handleri orqali ilovani ochishga yo'naltiriladi.
"""

import logging

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message

from core.database import async_session
from db.repositories import EmployeeRepository
from keyboards.miniapp_kb import build_miniapp_button
from services import registration_service
from states.registration_states import RegistrationStates

logger = logging.getLogger(__name__)

router = Router(name="common_start")

_OPEN_APP_TEXT = "📱 Barcha amallar Mini App ichida — pastdagi tugmani bosing."


def _miniapp_keyboard() -> InlineKeyboardMarkup | None:
    miniapp_button = build_miniapp_button()
    if miniapp_button is None:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[miniapp_button]])


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    try:
        async with async_session() as session:
            employee = await EmployeeRepository(session).get_by_telegram_id(message.from_user.id)

        if employee is not None:
            await message.answer(
                f"Xush kelibsiz, {employee.full_name}!\n\n{_OPEN_APP_TEXT}",
                reply_markup=_miniapp_keyboard(),
            )
            return

        await state.set_state(RegistrationStates.waiting_for_full_name)
        await message.answer(
            "Xush kelibsiz! Botdan foydalanish uchun avval ro'yxatdan o'tishingiz kerak.\n"
            "Iltimos, bazada ro'yxatdan o'tgan TO'LIQ ismingizni kiriting:"
        )
    except Exception:
        logger.exception("cmd_start xatosi (telegram_id=%s)", message.from_user.id)
        await message.answer("Kutilmagan xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring.")


@router.message(RegistrationStates.waiting_for_full_name)
async def on_full_name_received(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if not full_name:
        await message.answer("Ism bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return

    try:
        employee = await registration_service.link_employee_to_telegram(full_name, message.from_user.id)
    except registration_service.EmployeeNotFoundError:
        await message.answer(
            f"'{full_name}' ismli xodim bazada topilmadi. Ismni tekshirib qayta kiriting "
            "yoki administratorga murojaat qiling."
        )
        return
    except registration_service.AmbiguousNameError:
        await state.clear()
        await message.answer(
            f"'{full_name}' ismli bir nechta xodim topildi. Iltimos, administratorga murojaat qiling."
        )
        return
    except registration_service.AlreadyLinkedError:
        await state.clear()
        await message.answer(
            "Bu xodim allaqachon boshqa Telegram akkauntga bog'langan. Administratorga murojaat qiling."
        )
        return
    except Exception:
        logger.exception("on_full_name_received xatosi (full_name=%s)", full_name)
        await state.clear()
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await state.clear()
    logger.info("Xodim Telegramga bog'landi: %s (telegram_id=%s)", employee.full_name, employee.telegram_id)
    await message.answer(
        f"✅ Muvaffaqiyatli bog'landingiz, {employee.full_name}!\n\n{_OPEN_APP_TEXT}",
        reply_markup=_miniapp_keyboard(),
    )


@router.message(StateFilter(None))
async def on_any_other_message(message: Message) -> None:
    """Chat endi hech qanday /buyruq yoki tugmali menyuni qo'llab-quvvatlamaydi
    — faol FSM oqimi yo'q holatda kelgan HAR QANDAY xabar shu javobni oladi.
    (Faol FSM oqimi bo'lsa — masalan `/mijoz` yoki ro'yxatdan o'tish — bu
    handler `StateFilter(None)` tufayli ishga tushmaydi, oqim o'z holicha davom etadi.)"""
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_telegram_id(message.from_user.id)
    if employee is None:
        return  # ro'yxatdan o'tmagan foydalanuvchi — /start orqali yo'naltiriladi
    await message.answer(_OPEN_APP_TEXT, reply_markup=_miniapp_keyboard())
