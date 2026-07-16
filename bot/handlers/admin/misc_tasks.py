""""Vazifalar" moduli — Trello'siz, tizim ichida boshqariladigan alohida
topshiriqlar (9-band). Masalan: "Ofisni tozalash", "Hisobot tayyorlash".

Qadamlar: matn -> muddat -> xodimlar (ko'p tanlov, 3 tagacha) -> tasdiqlash.
Tasdiqlangach `task_service.create_misc_task()` chaqiriladi — bu Trello'ga
UMUMAN MUROJAAT QILMAYDI, faqat bazaga yozadi; so'ng bir xil
`notification_service.notify_task_started()` orqali xabar boradi (7.1-band
oqimidagi bilan bitta funksiya — MISC va ORDER xabarlari bir xil ko'rinishda).

Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR — RoleAccessMiddleware orqali.
"""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.repositories import EmployeeRepository
from keyboards.admin_kb import (
    CANCEL,
    CONFIRM,
    EMPLOYEES_DONE,
    EmployeeToggle,
    build_confirm_keyboard,
    build_employee_multiselect_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import notification_service, task_service
from states.misc_task_states import MiscTaskStates
from utils.enums import Role
from utils.formatters import format_dt

logger = logging.getLogger(__name__)

router = Router(name="admin_misc_tasks")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))
router.callback_query.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))

MAX_ASSIGNEES = 3

# Toshkent doim UTC+5 (task_create.py bilan bir xil qoida).
TASHKENT_TZ = timezone(timedelta(hours=5))


async def _list_active_employees():
    async with async_session() as session:
        return await EmployeeRepository(session).list_active()


async def _build_summary_text(data: dict) -> str:
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        names = []
        for employee_id in data["employee_ids"]:
            employee = await employee_repo.get_by_id(employee_id)
            if employee is not None:
                names.append(employee.full_name)

    deadline = datetime.fromisoformat(data["deadline"])
    return (
        "Topshiriqni tasdiqlang:\n\n"
        f"Matn: {data['text']}\n"
        f"Muddat: {format_dt(deadline)}\n"
        f"Xodimlar: {', '.join(names) if names else '-'}"
    )


@router.message(Command("addtask"))
async def cmd_add_task(message: Message, state: FSMContext) -> None:
    try:
        await state.set_state(MiscTaskStates.waiting_for_text)
        await state.update_data(employee_ids=[])
        await message.answer(
            "Yangi topshiriq matnini kiriting (masalan: \"Ofisni tozalash\") "
            "— bekor qilish uchun /cancel:"
        )
    except Exception:
        logger.exception("cmd_add_task xatosi (telegram_id=%s)", message.from_user.id)
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.message(Command("cancel"), StateFilter(MiscTaskStates))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Topshiriq yaratish bekor qilindi.")


@router.message(MiscTaskStates.waiting_for_text)
async def on_text_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Matn bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return

    await state.update_data(text=text)
    await state.set_state(MiscTaskStates.waiting_for_deadline)
    await message.answer("Muddatni kiriting (masalan: 25.07.2026 18:00):")


@router.message(MiscTaskStates.waiting_for_deadline)
async def on_deadline_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        naive = datetime.strptime(text, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("Format noto'g'ri. Masalan: 25.07.2026 18:00 shaklida kiriting:")
        return

    deadline = naive.replace(tzinfo=TASHKENT_TZ)

    employees = await _list_active_employees()
    if not employees:
        await message.answer("Bazada faol xodim topilmadi. Administratorga murojaat qiling.")
        await state.clear()
        return

    await state.update_data(deadline=deadline.isoformat())
    await state.set_state(MiscTaskStates.waiting_for_employees)
    await message.answer(
        f"Xodimlarni tanlang (ko'pi bilan {MAX_ASSIGNEES} ta), tugagach \"✅ Tayyor\" bosing:",
        reply_markup=build_employee_multiselect_keyboard(employees, set()),
    )


@router.callback_query(MiscTaskStates.waiting_for_employees, EmployeeToggle.filter())
async def on_employee_toggled(
    callback: CallbackQuery, callback_data: EmployeeToggle, state: FSMContext
) -> None:
    try:
        data = await state.get_data()
        selected: list[int] = list(data.get("employee_ids", []))

        if callback_data.employee_id in selected:
            selected.remove(callback_data.employee_id)
        elif len(selected) >= MAX_ASSIGNEES:
            await callback.answer(f"Ko'pi bilan {MAX_ASSIGNEES} ta xodim tanlash mumkin.", show_alert=True)
            return
        else:
            selected.append(callback_data.employee_id)

        await state.update_data(employee_ids=selected)

        employees = await _list_active_employees()
        if callback.message:
            await callback.message.edit_reply_markup(
                reply_markup=build_employee_multiselect_keyboard(employees, set(selected))
            )
        await callback.answer()
    except Exception:
        logger.exception("on_employee_toggled xatosi (employee_id=%s)", callback_data.employee_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(MiscTaskStates.waiting_for_employees, F.data == EMPLOYEES_DONE)
async def on_employees_done(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        if not data.get("employee_ids"):
            await callback.answer("Kamida bitta xodim tanlang.", show_alert=True)
            return

        await state.set_state(MiscTaskStates.confirming)
        summary = await _build_summary_text(data)

        if callback.message:
            await callback.message.edit_text(summary, reply_markup=build_confirm_keyboard())
        await callback.answer()
    except Exception:
        logger.exception("on_employees_done xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(MiscTaskStates.confirming, F.data == CANCEL)
async def on_cancelled(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Topshiriq yaratish bekor qilindi.")
    await callback.answer()


@router.callback_query(MiscTaskStates.confirming, F.data == CONFIRM)
async def on_confirmed(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()

    try:
        deadline = datetime.fromisoformat(data["deadline"])
        task = await task_service.create_misc_task(
            text=data["text"], deadline=deadline, employee_ids=data["employee_ids"]
        )
    except ValueError as exc:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_confirmed xatosi")
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Kutilmagan xatolik yuz berdi.")
        return

    await callback.answer("Topshiriq yaratildi ✅")
    if callback.message:
        try:
            await callback.message.edit_text(f"✅ Topshiriq yaratildi: {task.title}")
        except Exception:
            logger.exception("Xabarni yangilashda xatolik (task_id=%s)", task.id)

    try:
        await notification_service.notify_task_started(bot, task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)
