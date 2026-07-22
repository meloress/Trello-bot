"""Ro'yxatdan o'tish va rolga mos asosiy menyu (5.2-band).

`/start`: telegram_id bazada topilsa -> darhol roliga mos menyu. Topilmasa ->
FSM orqali to'liq ism so'raladi, `registration_service` orqali mavjud
xodim yozuviga bog'lanadi.
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from aiogram.types import InlineKeyboardMarkup

from core.database import async_session
from db.repositories import EmployeeRepository
from keyboards.miniapp_kb import build_miniapp_button
from keyboards.worker_kb import build_worker_menu_keyboard
from services import registration_service
from states.registration_states import RegistrationStates
from utils.enums import Role

logger = logging.getLogger(__name__)

router = Router(name="common_start")

_ROLE_MENUS = {
    Role.WORKER: "👷 Ishchi paneli\n\nQuyidagi bo'limlardan birini tanlang "
    "(yoki /tasks, /misctasks, /myscore komandalaridan foydalaning):",
    Role.ADMIN: "👔 Rahbar paneli\n\n/newtask — yangi vazifa yaratish\n/settings — tizim sozlamalari",
    Role.SUPERVISOR: "👔 Nazoratchi paneli\n\n/newtask — yangi vazifa yaratish\n/settings — tizim sozlamalari",
    Role.BRIGADIER: "👨‍💼 Brigadir paneli\n\n/brigade — brigadangiz KPI holati",
    Role.SELLER: "💼 Sotuvchi paneli\n\n/yangilid — yangi lid qo'shish\n/lidlarim — lidlar voronkasi",
}
_DEFAULT_MENU = "Ro'yxatdan o'tish muvaffaqiyatli. Sizning rolingiz uchun funksiyalar hali ishlab chiqilmoqda."


def _menu_for_role(role: Role) -> str:
    return _ROLE_MENUS.get(role, _DEFAULT_MENU)


def _keyboard_for_role(role: Role) -> InlineKeyboardMarkup | None:
    if role == Role.WORKER:
        return build_worker_menu_keyboard()

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
                f"Xush kelibsiz, {employee.full_name}!\n\n{_menu_for_role(employee.role)}",
                reply_markup=_keyboard_for_role(employee.role),
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
        f"✅ Muvaffaqiyatli bog'landingiz, {employee.full_name}!\n\n{_menu_for_role(employee.role)}",
        reply_markup=_keyboard_for_role(employee.role),
    )
