"""6.1/7.4-band: ko'p bosqichli buyurtma progressiyasi — PENDING_SETUP
bosqichga muddat va xodim(lar) belgilash oqimi.

`services/notification_service.notify_stage_pending_setup()` yuborgan
"Sozlash" tugmasi shu oqimni boshlaydi (`AdvanceTaskSetup` callback_data,
task_id shu yerdan olinadi). Qadamlar: muddat -> xodimlar (ko'p tanlov) ->
tasdiqlash. Tasdiqlangach `task_service.activate_pending_stage()` chaqiriladi
— karta joyi allaqachon `task_service.advance_task_stage()`da ko'chirilgan,
bu yerda faqat muddat/xodim yozilib taymer (`status=ACTIVE`) boshlanadi.

Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR — RoleAccessMiddleware orqali.
"""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.repositories import EmployeeRepository, TaskRepository
from keyboards.admin_kb import (
    CANCEL_TASK,
    CONFIRM_TASK,
    EMPLOYEES_DONE,
    AdvanceTaskSetup,
    EmployeeToggle,
    build_confirm_keyboard,
    build_employee_multiselect_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import notification_service, task_service
from states.advance_task_states import AdvanceTaskStates
from utils.enums import Role
from utils.formatters import format_dt

logger = logging.getLogger(__name__)

router = Router(name="admin_advance_task")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))
router.callback_query.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))

# Toshkent doim UTC+5 (task_create.py/misc_tasks.py bilan bir xil qoida).
TASHKENT_TZ = timezone(timedelta(hours=5))


async def _get_task_department_id(task_id: int) -> int | None:
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        return task.current_department_id if task else None


async def _list_department_employees(department_id: int):
    async with async_session() as session:
        return await EmployeeRepository(session).list_by_department(department_id)


async def _build_summary_text(data: dict) -> str:
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(data["task_id"])
        employee_repo = EmployeeRepository(session)
        names = []
        for employee_id in data["employee_ids"]:
            employee = await employee_repo.get_by_id(employee_id)
            if employee is not None:
                names.append(employee.full_name)

    deadline = datetime.fromisoformat(data["deadline"])
    title = task.title if task else "-"
    return (
        "Bosqichni tasdiqlang:\n\n"
        f"Buyurtma: {title}\n"
        f"Muddat: {format_dt(deadline)}\n"
        f"Xodimlar: {', '.join(names) if names else '-'}"
    )


@router.callback_query(StateFilter(None), AdvanceTaskSetup.filter())
async def on_advance_setup_started(
    callback: CallbackQuery, callback_data: AdvanceTaskSetup, state: FSMContext
) -> None:
    try:
        department_id = await _get_task_department_id(callback_data.task_id)
        if department_id is None:
            await callback.answer("Vazifa yoki bo'lim topilmadi.", show_alert=True)
            return

        await state.set_state(AdvanceTaskStates.waiting_for_deadline)
        await state.update_data(task_id=callback_data.task_id, employee_ids=[])
        if callback.message:
            await callback.message.answer(
                "Muddatni kiriting (masalan: 25.07.2026 18:00) — bekor qilish uchun /cancel:"
            )
        await callback.answer()
    except Exception:
        logger.exception("on_advance_setup_started xatosi (task_id=%s)", callback_data.task_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(Command("cancel"), StateFilter(AdvanceTaskStates))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bosqich sozlash bekor qilindi.")


@router.message(AdvanceTaskStates.waiting_for_deadline)
async def on_deadline_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        naive = datetime.strptime(text, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("Format noto'g'ri. Masalan: 25.07.2026 18:00 shaklida kiriting:")
        return

    deadline = naive.replace(tzinfo=TASHKENT_TZ)

    data = await state.get_data()
    department_id = await _get_task_department_id(data["task_id"])
    if department_id is None:
        await message.answer("Vazifa topilmadi.")
        await state.clear()
        return

    employees = await _list_department_employees(department_id)
    if not employees:
        await message.answer("Bu yo'nalishda faol xodim yo'q. Administratorga murojaat qiling.")
        await state.clear()
        return

    await state.update_data(deadline=deadline.isoformat())
    await state.set_state(AdvanceTaskStates.waiting_for_employees)
    await message.answer(
        "Xodimlarni tanlang (bir nechtasi mumkin), tugagach \"✅ Tayyor\" bosing:",
        reply_markup=build_employee_multiselect_keyboard(employees, set()),
    )


@router.callback_query(AdvanceTaskStates.waiting_for_employees, EmployeeToggle.filter())
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

        department_id = await _get_task_department_id(data["task_id"])
        employees = await _list_department_employees(department_id) if department_id else []
        if callback.message:
            await callback.message.edit_reply_markup(
                reply_markup=build_employee_multiselect_keyboard(employees, set(selected))
            )
        await callback.answer()
    except Exception:
        logger.exception("on_employee_toggled xatosi (employee_id=%s)", callback_data.employee_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(AdvanceTaskStates.waiting_for_employees, F.data == EMPLOYEES_DONE)
async def on_employees_done(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        if not data.get("employee_ids"):
            await callback.answer("Kamida bitta xodim tanlang.", show_alert=True)
            return

        await state.set_state(AdvanceTaskStates.confirming)
        summary = await _build_summary_text(data)

        if callback.message:
            await callback.message.edit_text(summary, reply_markup=build_confirm_keyboard())
        await callback.answer()
    except Exception:
        logger.exception("on_employees_done xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(AdvanceTaskStates.confirming, F.data == CANCEL_TASK)
async def on_cancel_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Bosqich sozlash bekor qilindi.")
    await callback.answer()


@router.callback_query(AdvanceTaskStates.confirming, F.data == CONFIRM_TASK)
async def on_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()

    try:
        deadline = datetime.fromisoformat(data["deadline"])
        task = await task_service.activate_pending_stage(
            data["task_id"], deadline=deadline, employee_ids=data["employee_ids"]
        )
    except task_service.TaskNotFoundError:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Xatolik: vazifa topilmadi.")
        return
    except task_service.InvalidTaskStateError as exc:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_confirm xatosi (task_id=%s)", data.get("task_id"))
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Kutilmagan xatolik yuz berdi.")
        return

    await callback.answer("Bosqich faollashtirildi ✅")
    if callback.message:
        try:
            await callback.message.edit_text(f"✅ Bosqich faollashtirildi: {task.title}")
        except Exception:
            logger.exception("Xabarni yangilashda xatolik (task_id=%s)", task.id)

    try:
        await notification_service.notify_task_started(bot, task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)
