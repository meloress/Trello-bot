"""Brigadir oynasi — "Brigadam statistikasi" (11.1-band).

Ruxsat: faqat Role.BRIGADIER/Role.SUPERVISOR — RoleAccessMiddleware orqali.

Oqim: `/brigade` -> BRIGADIER uchun o'zi boshqaradigan brigada avtomatik
topiladi; SUPERVISOR uchun brigadalar ro'yxatidan birini tanlaydi (o'z
bo'limi doirasida, bo'lim belgilanmagan bo'lsa — barcha brigadalar). Keyin
brigada a'zolari va ularning JORIY OY KPI holati ko'rsatiladi; har bir
xodim uchun ikkita tugma — "oxirgi 7 kunlik hisobot" va "joriy vazifalar".

Ma'lumotlar `stats_service.py` orqali, faqat shu brigadaga (`brigade_id`)
a'zo xodimlar bo'yicha filtrlangan holda olinadi — butun tizim skanerlanmaydi.
"""

import logging

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.database import async_session
from db.models.brigade import Brigade
from db.models.employee import Employee
from db.repositories import BrigadeRepository, TaskAssignmentRepository, TaskRepository
from keyboards.admin_kb import BrigadeSelect
from keyboards.brigadier_kb import CURRENT_TASKS, WEEKLY_REPORT, BrigadeMemberAction, build_brigade_member_keyboard
from middlewares.auth import RoleAccessMiddleware
from services import stats_service
from utils.enums import Role, TaskStatus
from utils.formatters import format_dt

logger = logging.getLogger(__name__)

router = Router(name="brigadier_stats")
router.message.middleware(RoleAccessMiddleware({Role.BRIGADIER, Role.SUPERVISOR}))
router.callback_query.middleware(RoleAccessMiddleware({Role.BRIGADIER, Role.SUPERVISOR}))

_TASK_STATUS_LABELS = {
    TaskStatus.ACTIVE: "🟢 Faol",
    TaskStatus.STOPPED: "🛑 To'xtatilgan",
    TaskStatus.COMPLETED: "✅ Yakunlangan",
    TaskStatus.OVERDUE: "🔴 Muddati o'tgan",
}


async def _find_led_brigade(employee_id: int) -> Brigade | None:
    async with async_session() as session:
        return await BrigadeRepository(session).get_by_brigadier_id(employee_id)


async def _list_brigades_for_supervisor(employee: Employee) -> list[Brigade]:
    async with async_session() as session:
        brigade_repo = BrigadeRepository(session)
        if employee.department_id is not None:
            return await brigade_repo.list_by_department(employee.department_id)
        return await brigade_repo.list_all()


def _build_brigade_select_keyboard(brigades: list[Brigade]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=b.name, callback_data=BrigadeSelect(brigade_id=b.id).pack())]
        for b in brigades
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_brigade_overview(brigade_name: str, stats: list[stats_service.EmployeeStats]) -> str:
    if not stats:
        return f"👥 {brigade_name}\n\nBrigadada faol xodim yo'q."

    lines = [f"👥 {brigade_name} — joriy oy KPI holati:", ""]
    for s in stats:
        lines.append(
            f"• {s.full_name}: {s.total_score:+d} ball, {s.penalty_count} jarima, "
            f"{s.completed_tasks} vazifa bajarilgan"
        )
    return "\n".join(lines)


async def _show_brigade_overview(answer_func, brigade: Brigade) -> None:
    stats = await stats_service.get_brigade_monthly_stats(brigade.id)
    text = _format_brigade_overview(brigade.name, stats)
    await answer_func(text, reply_markup=build_brigade_member_keyboard(stats))


async def _list_active_tasks(employee_id: int):
    async with async_session() as session:
        assignment_repo = TaskAssignmentRepository(session)
        task_repo = TaskRepository(session)

        assignments = await assignment_repo.list_by_employee(employee_id)
        tasks = []
        for assignment in assignments:
            task = await task_repo.get_by_id(assignment.task_id)
            if task is not None and task.status != TaskStatus.COMPLETED:
                tasks.append(task)
        return tasks


@router.message(Command("brigade"))
async def cmd_brigade(message: Message, employee: Employee) -> None:
    try:
        if employee.role == Role.BRIGADIER:
            brigade = await _find_led_brigade(employee.id)
            if brigade is None:
                await message.answer("Sizga biriktirilgan brigada topilmadi. Administratorga murojaat qiling.")
                return
            await _show_brigade_overview(message.answer, brigade)
            return

        # SUPERVISOR
        brigades = await _list_brigades_for_supervisor(employee)
        if not brigades:
            await message.answer("Ko'rish uchun brigada topilmadi.")
            return
        await message.answer("Qaysi brigadani ko'rmoqchisiz?", reply_markup=_build_brigade_select_keyboard(brigades))
    except Exception:
        logger.exception("cmd_brigade xatosi (telegram_id=%s)", message.from_user.id)
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.callback_query(StateFilter(None), BrigadeSelect.filter())
async def on_supervisor_brigade_selected(callback: CallbackQuery, callback_data: BrigadeSelect) -> None:
    # `StateFilter(None)` ataylab qo'yilgan: `BrigadeSelect` boshqa routerlarda
    # (employee_management.py) ham ishlatiladi, lekin har doim aniq FSM
    # holatiga bog'langan holda. Bu handler faqat foydalanuvchi HECH QANDAY
    # FSM holatida bo'lmaganda ishlaydi — shu orqali ular bir-biriga
    # aralashmaydi (har ikkalasi ham bitta callback_data sinfini ishlatsa ham).
    try:
        async with async_session() as session:
            brigade = await BrigadeRepository(session).get_by_id(callback_data.brigade_id)
        if brigade is None:
            await callback.answer("Brigada topilmadi.", show_alert=True)
            return

        if callback.message:
            await _show_brigade_overview(callback.message.answer, brigade)
        await callback.answer()
    except Exception:
        logger.exception("on_supervisor_brigade_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(BrigadeMemberAction.filter())
async def on_member_action(callback: CallbackQuery, callback_data: BrigadeMemberAction) -> None:
    try:
        if callback_data.action == WEEKLY_REPORT:
            stats = await stats_service.get_employee_weekly_stats(callback_data.employee_id)
            if stats is None:
                await callback.answer("Xodim topilmadi.", show_alert=True)
                return
            text = (
                f"📅 {stats.full_name} — oxirgi 7 kunlik hisobot:\n\n"
                f"Bajarilgan vazifalar: {stats.completed_tasks}\n"
                f"Jami ball: {stats.total_score:+d}\n"
                f"Jarimalar soni: {stats.penalty_count}"
            )
            if callback.message:
                await callback.message.answer(text)

        elif callback_data.action == CURRENT_TASKS:
            tasks = await _list_active_tasks(callback_data.employee_id)
            if not tasks:
                text = "📋 Joriy faol vazifalar yo'q."
            else:
                lines = ["📋 Joriy vazifalar:", ""]
                for task in tasks:
                    label = _TASK_STATUS_LABELS.get(task.status, str(task.status))
                    lines.append(f"• {task.title} — {label} — muddat: {format_dt(task.deadline)}")
                text = "\n".join(lines)
            if callback.message:
                await callback.message.answer(text)

        await callback.answer()
    except Exception:
        logger.exception("on_member_action xatosi (action=%s)", callback_data.action)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
