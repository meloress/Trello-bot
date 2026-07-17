"""Ishchi oynasi: vazifalar ro'yxati va Boshlash/Stop/Davom ettirish/Yakunlash
oqimlari (7 va 11-band).

Har bir callback handler ikki qismga bo'lingan: (1) asosiy biznes amali —
`timer_service`/`penalty_service` chaqiruvi, muvaffaqiyatsiz bo'lsa aniq xato
xabari bilan darhol to'xtaydi; (2) ikkinchi darajali ta'sirlar — bildirishnoma
va UI yangilanishi, bular muvaffaqiyatsiz bo'lsa ham ASOSIY amal allaqachon
bajarilgan bo'lgani uchun xodimga soxta "xatolik" xabari ko'rsatilmaydi,
faqat log qilinadi.

Xodim<->Telegram bog'lanishi hozircha shu faylda mahalliy (`_get_employee`)
hal qilinadi — kelajakda `middlewares/auth.py` markazlashtirilganda shu yerga
ko'chiriladi.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.models.employee import Employee
from db.models.task import Task
from db.repositories import EmployeeRepository, TaskAssignmentRepository, TaskRepository
from keyboards.worker_kb import TaskAction, build_task_keyboard
from services import notification_service, penalty_service, task_service, timer_service
from states.task_states import StopTaskStates
from utils.enums import TaskStatus, TaskType
from utils.formatters import format_dt

logger = logging.getLogger(__name__)

router = Router(name="worker_tasks")

_STATUS_LABELS = {
    TaskStatus.ACTIVE: "🟢 Faol",
    TaskStatus.STOPPED: "🛑 To'xtatilgan",
    TaskStatus.COMPLETED: "✅ Yakunlangan",
    TaskStatus.OVERDUE: "🔴 Muddati o'tgan",
    TaskStatus.PENDING_SETUP: "⏳ Navbatda (sozlanmoqda)",
}


async def _get_employee(telegram_id: int) -> Employee | None:
    async with async_session() as session:
        return await EmployeeRepository(session).get_by_telegram_id(telegram_id)


async def _list_my_tasks(employee_id: int) -> list[Task]:
    """Xodimga biriktirilgan, hali yakunlanmagan vazifalar."""
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


def _format_task_text(task: Task) -> str:
    label = _STATUS_LABELS.get(task.status, str(task.status))
    type_tag = f"[{task.task_type.value.upper()}] "
    # PENDING_SETUP holatida deadline hali yo'q (6.1/7.4-band: nazoratchi
    # hali muddat kiritmagan) — format_dt(None) yiqilmasligi uchun himoya.
    deadline_text = format_dt(task.deadline) if task.deadline is not None else "hali belgilanmagan"
    return f"{type_tag}{task.title}\nHolat: {label}\nMuddat: {deadline_text}"


@router.message(Command("tasks", "mytasks"))
async def cmd_tasks(message: Message) -> None:
    try:
        employee = await _get_employee(message.from_user.id)
        if employee is None:
            await message.answer("Siz tizimda ro'yxatdan o'tmagansiz. Administratorga murojaat qiling.")
            return

        tasks = await _list_my_tasks(employee.id)
        if not tasks:
            await message.answer("Sizga biriktirilgan faol vazifalar yo'q.")
            return

        for task in tasks:
            await message.answer(_format_task_text(task), reply_markup=build_task_keyboard(task))
    except Exception:
        logger.exception("cmd_tasks xatosi (telegram_id=%s)", message.from_user.id)
        await message.answer("Kechirasiz, vazifalarni yuklashda xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring.")


@router.callback_query(TaskAction.filter(F.action == "start"))
async def on_start_task(callback: CallbackQuery, callback_data: TaskAction, bot: Bot) -> None:
    try:
        employee = await _get_employee(callback.from_user.id)
        if employee is None:
            await callback.answer("Siz ro'yxatdan o'tmagansiz.", show_alert=True)
            return
        task = await timer_service.start_task(callback_data.task_id, [employee.id])
    except timer_service.TaskNotFoundError:
        await callback.answer("Vazifa topilmadi.", show_alert=True)
        return
    except timer_service.InvalidTaskStateError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        logger.exception("on_start_task xatosi (task_id=%s)", callback_data.task_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    try:
        await notification_service.notify_task_started(bot, task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)

    try:
        if callback.message:
            await callback.message.edit_text(_format_task_text(task), reply_markup=build_task_keyboard(task))
    except Exception:
        logger.exception("Xabarni yangilashda xatolik (task_id=%s)", task.id)

    await callback.answer("Vazifa boshlandi ✅")


@router.callback_query(TaskAction.filter(F.action == "stop"))
async def on_stop_task_requested(callback: CallbackQuery, callback_data: TaskAction, state: FSMContext) -> None:
    try:
        await state.set_state(StopTaskStates.waiting_for_reason)
        await state.update_data(task_id=callback_data.task_id)
        if callback.message:
            await callback.message.answer("To'xtatish sababini yozing:")
        await callback.answer()
    except Exception:
        logger.exception("on_stop_task_requested xatosi (task_id=%s)", callback_data.task_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(StopTaskStates.waiting_for_reason)
async def on_stop_reason_received(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    task_id = data.get("task_id")
    reason = (message.text or "").strip()

    if not reason:
        await message.answer("Sabab bo'sh bo'lishi mumkin emas. Iltimos, matn kiriting:")
        return

    if task_id is None:
        await state.clear()
        await message.answer("Xatolik: vazifa aniqlanmadi. Qaytadan /tasks orqali urinib ko'ring.")
        return

    try:
        employee = await _get_employee(message.from_user.id)
        if employee is None:
            await state.clear()
            await message.answer("Siz ro'yxatdan o'tmagansiz.")
            return

        stop_log = await timer_service.stop_task(task_id, employee.id, reason)
    except timer_service.TaskNotFoundError:
        await state.clear()
        await message.answer("Vazifa topilmadi.")
        return
    except (timer_service.InvalidTaskStateError, ValueError) as exc:
        await state.clear()
        await message.answer(f"Amalni bajarib bo'lmadi: {exc}")
        return
    except Exception:
        logger.exception("on_stop_reason_received xatosi (task_id=%s)", task_id)
        await state.clear()
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await state.clear()

    try:
        await notification_service.notify_task_stopped(bot, stop_log.id)
    except Exception:
        logger.exception("notify_task_stopped xatosi (stop_log_id=%s)", stop_log.id)

    try:
        await notification_service.notify_client_task_stopped(bot, stop_log.id)
    except Exception:
        logger.exception("notify_client_task_stopped xatosi (stop_log_id=%s)", stop_log.id)

    try:
        async with async_session() as session:
            task = await TaskRepository(session).get_by_id(task_id)
        if task is not None:
            await message.answer(
                "Vazifa to'xtatildi. ✅ Sabab qayd etildi.\n\n" + _format_task_text(task),
                reply_markup=build_task_keyboard(task),
            )
            return
    except Exception:
        logger.exception("Vazifani qayta ko'rsatishda xatolik (task_id=%s)", task_id)

    await message.answer("Vazifa to'xtatildi. ✅ Sabab qayd etildi.")


@router.callback_query(TaskAction.filter(F.action == "resume"))
async def on_resume_task(callback: CallbackQuery, callback_data: TaskAction) -> None:
    try:
        task = await timer_service.resume_task(callback_data.task_id)
    except timer_service.TaskNotFoundError:
        await callback.answer("Vazifa topilmadi.", show_alert=True)
        return
    except timer_service.InvalidTaskStateError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        logger.exception("on_resume_task xatosi (task_id=%s)", callback_data.task_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    try:
        if callback.message:
            await callback.message.edit_text(_format_task_text(task), reply_markup=build_task_keyboard(task))
    except Exception:
        logger.exception("Xabarni yangilashda xatolik (task_id=%s)", task.id)

    await callback.answer("Vazifa davom ettirildi ▶️")


@router.callback_query(TaskAction.filter(F.action == "finish"))
async def on_finish_task(callback: CallbackQuery, callback_data: TaskAction, bot: Bot) -> None:
    try:
        task = await timer_service.finish_task(callback_data.task_id)
    except timer_service.TaskNotFoundError:
        await callback.answer("Vazifa topilmadi.", show_alert=True)
        return
    except timer_service.InvalidTaskStateError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        logger.exception("on_finish_task xatosi (task_id=%s)", callback_data.task_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    try:
        if callback.message:
            await callback.message.edit_text(_format_task_text(task), reply_markup=build_task_keyboard(task))
    except Exception:
        logger.exception("Xabarni yangilashda xatolik (task_id=%s)", task.id)

    await callback.answer("Vazifa yakunlandi ✅")

    # 8.1/8.2-band: kechikish bo'lsa jarima, bo'lmasa bo'sh ro'yxat qaytadi.
    # Qoida hali sozlanmagan (PenaltyRuleNotConfiguredError) bo'lsa ham xodimning
    # "Yakunlash" amali muvaffaqiyatli qolishi kerak — faqat log qilinadi.
    try:
        kpi_logs = await penalty_service.calculate_and_apply_task_penalty(task.id)
    except penalty_service.PenaltyRuleNotConfiguredError:
        logger.warning("Task %s uchun kechikish qoidasi topilmadi (admin penalty_rules'ga qo'shishi kerak)", task.id)
        kpi_logs = []
    except Exception:
        logger.exception("calculate_and_apply_task_penalty xatosi (task_id=%s)", task.id)
        kpi_logs = []

    for kpi_log in kpi_logs:
        try:
            await notification_service.notify_penalty_applied(bot, kpi_log.id)
        except Exception:
            logger.exception("notify_penalty_applied xatosi (kpi_log_id=%s)", kpi_log.id)

    # 6.1/7.4-band: ko'p bosqichli buyurtma progressiyasi. Faqat ORDER turi
    # uchun (MISC — 9-band — Trello/bo'lim zanjiriga umuman aloqasi yo'q).
    # Ikkinchi-darajali ta'sir sifatida: xato bo'lsa ham ishchining "Yakunlash"
    # amali (yuqorida) allaqachon muvaffaqiyatli bo'lgan, faqat log qilinadi.
    if task.task_type == TaskType.ORDER:
        try:
            next_task = await task_service.advance_task_stage(task.id)
        except Exception:
            logger.exception("advance_task_stage xatosi (task_id=%s)", task.id)
            next_task = None

        # 12-band: "mahsulot bo'limdan CHIQQANDA" — next_task None (buyurtma
        # to'liq tugagan) bo'lsa ham, bosqichdan chiqish hodisasi shu.
        try:
            await notification_service.notify_client_stage_advanced(bot, task.id)
        except Exception:
            logger.exception("notify_client_stage_advanced xatosi (task_id=%s)", task.id)

        if next_task is not None:
            try:
                await notification_service.notify_stage_pending_setup(bot, next_task.id)
            except Exception:
                logger.exception("notify_stage_pending_setup xatosi (task_id=%s)", next_task.id)
