"""Rahbar/nazoratchi uchun yangi vazifa yaratish oqimi (7.1-band).

Qadamlar: nom -> tavsif -> muddat -> yo'nalish -> xodimlar (ko'p tanlov) ->
tasdiqlash. Tasdiqlangandan keyingina `task_service.create_task()` chaqiriladi
— u AVVAL Trello'da karta ochadi, FAQAT shu muvaffaqiyatli bo'lsa bazaga
yozadi. Muvaffaqiyatdan keyin `notification_service.notify_task_started()`
orqali biriktirilgan xodimlarga xabar boradi.
"""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.models.employee import Employee
from db.repositories import ClientRepository, DepartmentRepository, EmployeeRepository
from keyboards.admin_kb import (
    CANCEL_TASK,
    CONFIRM_TASK,
    EMPLOYEES_DONE,
    SKIP,
    DepartmentSelect,
    EmployeeToggle,
    build_client_phone_skip_keyboard,
    build_confirm_keyboard,
    build_department_keyboard,
    build_employee_multiselect_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import client_service, notification_service, task_service
from states.task_states import CreateTaskStates
from trello.client import TrelloAPIError
from utils.enums import Role
from utils.formatters import format_dt

logger = logging.getLogger(__name__)

router = Router(name="admin_task_create")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))
router.callback_query.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))

# Toshkent doim UTC+5 (notification_service/utils.formatters bilan bir xil qoida).
TASHKENT_TZ = timezone(timedelta(hours=5))


async def _list_configured_departments():
    async with async_session() as session:
        departments = await DepartmentRepository(session).list_all()
        return [d for d in departments if d.trello_list_id]


async def _list_department_employees(department_id: int) -> list[Employee]:
    async with async_session() as session:
        return await EmployeeRepository(session).list_by_department(department_id)


async def _build_summary_text(data: dict) -> str:
    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(data["department_id"])
        employee_repo = EmployeeRepository(session)
        names = []
        for employee_id in data["employee_ids"]:
            employee = await employee_repo.get_by_id(employee_id)
            if employee is not None:
                names.append(employee.full_name)

        client_name = None
        if data.get("client_id"):
            client = await ClientRepository(session).get_by_id(data["client_id"])
            client_name = client.full_name if client else None

    deadline = datetime.fromisoformat(data["deadline"])
    lines = ["Vazifani tasdiqlang:", f"Nomi: {data['title']}"]
    if data.get("description"):
        lines.append(f"Tavsif: {data['description']}")
    lines.append(f"Muddat: {format_dt(deadline)}")
    lines.append(f"Yo'nalish: {department.name if department else '-'}")
    lines.append(f"Xodimlar: {', '.join(names) if names else '-'}")
    lines.append(f"Mijoz: {client_name or '-'}")
    return "\n".join(lines)


@router.message(Command("newtask"))
async def cmd_new_task(message: Message, state: FSMContext) -> None:
    try:
        await state.set_state(CreateTaskStates.waiting_for_title)
        await state.update_data(employee_ids=[])
        await message.answer("Yangi vazifa nomini kiriting (bekor qilish uchun /cancel):")
    except Exception:
        logger.exception("cmd_new_task xatosi (telegram_id=%s)", message.from_user.id)
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.message(Command("cancel"), StateFilter(CreateTaskStates))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Vazifa yaratish bekor qilindi.")


@router.message(CreateTaskStates.waiting_for_title)
async def on_title_received(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Nom bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return

    await state.update_data(title=title)
    await state.set_state(CreateTaskStates.waiting_for_description)
    await message.answer("Tavsifni kiriting (agar kerak bo'lmasa, '-' deb yozing):")


@router.message(CreateTaskStates.waiting_for_description)
async def on_description_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    description = None if text == "-" else text

    await state.update_data(description=description)
    await state.set_state(CreateTaskStates.waiting_for_deadline)
    await message.answer("Muddatni kiriting (masalan: 25.07.2026 18:00):")


@router.message(CreateTaskStates.waiting_for_deadline)
async def on_deadline_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        naive = datetime.strptime(text, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("Format noto'g'ri. Masalan: 25.07.2026 18:00 shaklida kiriting:")
        return

    deadline = naive.replace(tzinfo=TASHKENT_TZ)

    try:
        departments = await _list_configured_departments()
    except Exception:
        logger.exception("_list_configured_departments xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")
        await state.clear()
        return

    if not departments:
        await message.answer(
            "Hech qanday yo'nalish uchun Trello ro'yxati (list) sozlanmagan. Administratorga murojaat qiling."
        )
        await state.clear()
        return

    await state.update_data(deadline=deadline.isoformat())
    await state.set_state(CreateTaskStates.waiting_for_department)
    await message.answer("Yo'nalishni tanlang:", reply_markup=build_department_keyboard(departments))


@router.callback_query(CreateTaskStates.waiting_for_department, DepartmentSelect.filter())
async def on_department_selected(
    callback: CallbackQuery, callback_data: DepartmentSelect, state: FSMContext
) -> None:
    try:
        employees = await _list_department_employees(callback_data.department_id)
        if not employees:
            await callback.answer("Bu yo'nalishda faol xodim yo'q.", show_alert=True)
            return

        await state.update_data(department_id=callback_data.department_id, employee_ids=[])
        await state.set_state(CreateTaskStates.waiting_for_employees)

        if callback.message:
            await callback.message.edit_text(
                "Xodimlarni tanlang (bir nechtasi mumkin), tugagach \"✅ Tayyor\" bosing:",
                reply_markup=build_employee_multiselect_keyboard(employees, set()),
            )
        await callback.answer()
    except Exception:
        logger.exception("on_department_selected xatosi (department_id=%s)", callback_data.department_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(CreateTaskStates.waiting_for_employees, EmployeeToggle.filter())
async def on_employee_toggled(
    callback: CallbackQuery, callback_data: EmployeeToggle, state: FSMContext
) -> None:
    try:
        data = await state.get_data()
        selected: list[int] = list(data.get("employee_ids", []))
        if callback_data.employee_id in selected:
            selected.remove(callback_data.employee_id)
        else:
            selected.append(callback_data.employee_id)
        await state.update_data(employee_ids=selected)

        employees = await _list_department_employees(data["department_id"])
        if callback.message:
            await callback.message.edit_reply_markup(
                reply_markup=build_employee_multiselect_keyboard(employees, set(selected))
            )
        await callback.answer()
    except Exception:
        logger.exception("on_employee_toggled xatosi (employee_id=%s)", callback_data.employee_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(CreateTaskStates.waiting_for_employees, F.data == EMPLOYEES_DONE)
async def on_employees_done(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        if not data.get("employee_ids"):
            await callback.answer("Kamida bitta xodim tanlang.", show_alert=True)
            return

        await state.set_state(CreateTaskStates.waiting_for_client_phone)

        if callback.message:
            await callback.message.edit_text(
                "Mijoz telefon raqamini kiriting (12-band: bosqich o'tganda/\"Stop\" "
                "bosilganda mijozga avtomatik xabar borishi uchun, ixtiyoriy):",
                reply_markup=build_client_phone_skip_keyboard(),
            )
        await callback.answer()
    except Exception:
        logger.exception("on_employees_done xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


async def _show_confirmation(answer_func, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(CreateTaskStates.confirming)
    summary = await _build_summary_text(data)
    await answer_func(summary, reply_markup=build_confirm_keyboard())


@router.callback_query(CreateTaskStates.waiting_for_client_phone, F.data == SKIP)
async def on_client_phone_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        if callback.message:
            await _show_confirmation(callback.message.edit_text, state)
        await callback.answer()
    except Exception:
        logger.exception("on_client_phone_skipped xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(CreateTaskStates.waiting_for_client_phone)
async def on_client_phone_received(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if not phone or phone == "-":
        await _show_confirmation(message.answer, state)
        return

    await state.update_data(client_phone=phone)
    await state.set_state(CreateTaskStates.waiting_for_client_name)
    await message.answer("Mijoz F.I.Sh. kiriting:")


@router.message(CreateTaskStates.waiting_for_client_name)
async def on_client_name_received(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if not full_name:
        await message.answer("Ism bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return

    try:
        data = await state.get_data()
        client = await client_service.find_or_create_client(
            phone_number=data["client_phone"], full_name=full_name
        )
        await state.update_data(client_id=client.id)
    except Exception:
        logger.exception("on_client_name_received xatosi")
        await state.clear()
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await _show_confirmation(message.answer, state)


@router.callback_query(CreateTaskStates.confirming, F.data == CANCEL_TASK)
async def on_cancel_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Vazifa yaratish bekor qilindi.")
    await callback.answer()


@router.callback_query(CreateTaskStates.confirming, F.data == CONFIRM_TASK)
async def on_confirm_task(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()

    try:
        deadline = datetime.fromisoformat(data["deadline"])
        task = await task_service.create_task(
            title=data["title"],
            description=data.get("description"),
            deadline=deadline,
            department_id=data["department_id"],
            employee_ids=data["employee_ids"],
            client_id=data.get("client_id"),
        )
    except task_service.DepartmentNotFoundError:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Xatolik: yo'nalish topilmadi.")
        return
    except task_service.DepartmentNotConfiguredError as exc:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(f"Xatolik: {exc}")
        return
    except TrelloAPIError:
        logger.exception("Trello karta yaratishda xatolik")
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                "Trello bilan bog'lanishda xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring (/newtask)."
            )
        return
    except Exception:
        logger.exception("on_confirm_task xatosi")
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Kutilmagan xatolik yuz berdi.")
        return

    await callback.answer("Vazifa yaratildi ✅")
    if callback.message:
        try:
            await callback.message.edit_text(f"✅ Vazifa yaratildi: {task.title}\nTrello karta: {task.trello_card_id}")
        except Exception:
            logger.exception("Xabarni yangilashda xatolik (task_id=%s)", task.id)

    try:
        await notification_service.notify_task_started(bot, task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)
