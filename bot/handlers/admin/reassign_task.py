"""8.3-band: uzoq kechikkan (OVERDUE, 48 soatdan ortiq) buyurtmani boshqa
brigadaga QO'LDA o'tkazish oqimi. Avtomatik qism (aniqlash+signal, "Ko'rib
chiqish" tugmasi) `jobs/overdue_watch_job.py`da; yakuniy brigada tanlovi va
tasdiq shu yerda — tizim o'zi brigada tanlamaydi (TZ 8.3-band talabi).

Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR — RoleAccessMiddleware orqali.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from core.database import async_session
from db.repositories import BrigadeRepository, EmployeeRepository, TaskAssignmentRepository, TaskRepository
from keyboards.admin_kb import (
    CANCEL_TASK,
    CONFIRM_TASK,
    BrigadeSelect,
    ReassignReview,
    build_brigade_keyboard,
    build_confirm_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import notification_service, task_service
from states.reassign_task_states import ReassignTaskStates
from utils.enums import Role

logger = logging.getLogger(__name__)

router = Router(name="admin_reassign_task")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))
router.callback_query.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))


async def _get_task_brigade_and_department(task_id: int) -> tuple[int | None, int | None]:
    """Task hozir tegishli bo'lgan brigada_id (birinchi biriktirilgan xodim
    orqali) va bo'lim_id."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            return None, None
        assignments = await TaskAssignmentRepository(session).list_by_task(task_id)
        employee_repo = EmployeeRepository(session)
        for assignment in assignments:
            employee = await employee_repo.get_by_id(assignment.employee_id)
            if employee is not None and employee.brigade_id is not None:
                return employee.brigade_id, task.current_department_id
        return None, task.current_department_id


@router.callback_query(StateFilter(None), ReassignReview.filter())
async def on_reassign_review_started(
    callback: CallbackQuery, callback_data: ReassignReview, state: FSMContext
) -> None:
    try:
        current_brigade_id, department_id = await _get_task_brigade_and_department(callback_data.task_id)
        if department_id is None:
            await callback.answer("Vazifa yoki bo'lim topilmadi.", show_alert=True)
            return

        async with async_session() as session:
            brigades = await BrigadeRepository(session).list_by_department(department_id)
        options = [b for b in brigades if b.id != current_brigade_id]

        if not options:
            await callback.answer("Bu bo'limda boshqa brigada yo'q.", show_alert=True)
            return

        await state.set_state(ReassignTaskStates.waiting_for_brigade)
        await state.update_data(task_id=callback_data.task_id)
        if callback.message:
            await callback.message.answer(
                "Qaysi brigadaga o'tkazasiz?",
                reply_markup=build_brigade_keyboard(options, include_skip=False),
            )
        await callback.answer()
    except Exception:
        logger.exception("on_reassign_review_started xatosi (task_id=%s)", callback_data.task_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(ReassignTaskStates.waiting_for_brigade, BrigadeSelect.filter())
async def on_reassign_brigade_selected(
    callback: CallbackQuery, callback_data: BrigadeSelect, state: FSMContext
) -> None:
    try:
        async with async_session() as session:
            brigade = await BrigadeRepository(session).get_by_id(callback_data.brigade_id)
        if brigade is None:
            await callback.answer("Brigada topilmadi.", show_alert=True)
            return

        await state.update_data(brigade_id=callback_data.brigade_id)
        await state.set_state(ReassignTaskStates.confirming)
        if callback.message:
            await callback.message.edit_text(
                f"\"{brigade.name}\" brigadasiga o'tkazishni tasdiqlaysizmi?\n"
                "Eski brigadaga darhol jarima yoziladi.",
                reply_markup=build_confirm_keyboard(),
            )
        await callback.answer()
    except Exception:
        logger.exception("on_reassign_brigade_selected xatosi (brigade_id=%s)", callback_data.brigade_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(ReassignTaskStates.confirming, F.data == CANCEL_TASK)
async def on_reassign_cancelled(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.callback_query(ReassignTaskStates.confirming, F.data == CONFIRM_TASK)
async def on_reassign_confirmed(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    task_id = data["task_id"]
    new_brigade_id = data["brigade_id"]

    async with async_session() as session:
        old_employee_ids = [
            a.employee_id for a in await TaskAssignmentRepository(session).list_by_task(task_id)
        ]

    try:
        await task_service.reassign_task_brigade(task_id, new_brigade_id)
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
    except ValueError as exc:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_reassign_confirmed xatosi (task_id=%s)", task_id)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Kutilmagan xatolik yuz berdi.")
        return

    async with async_session() as session:
        new_employee_ids = [e.id for e in await EmployeeRepository(session).list_by_brigade(new_brigade_id)]

    await callback.answer("Brigadaga o'tkazildi ✅")
    if callback.message:
        await callback.message.edit_text("✅ Buyurtma boshqa brigadaga o'tkazildi.")

    try:
        await notification_service.notify_task_reassigned(
            bot, task_id, old_employee_ids=old_employee_ids, new_employee_ids=new_employee_ids
        )
    except Exception:
        logger.exception("notify_task_reassigned xatosi (task_id=%s)", task_id)
