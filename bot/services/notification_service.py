"""Telegram bildirishnomalari (3-band: faqat kartaga BELGILANGAN odamlarga signal).

`timer_service`/`penalty_service` singari, DB o'qish o'z sessiyasini ochib-yopadi.
Bu servis yozuv qilmaydi (faqat o'qiydi + xabar yuboradi), shu sababli commit yo'q.
Har bir yuborish `_send()` orqali izolyatsiya qilingan: bitta xodimga xabar
yuborilmay qolishi (masalan, botni bloklagan) qolganlarga ta'sir qilmaydi va
tizimni qulatmaydi.
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

from core.database import async_session
from db.models.task import Task
from db.repositories import (
    BrigadeRepository,
    DepartmentRepository,
    EmployeeRepository,
    KpiLogRepository,
    StopLogRepository,
    TaskAssignmentRepository,
    TaskRepository,
)
from keyboards.admin_kb import ReassignReview, build_advance_setup_keyboard, build_reassign_review_keyboard
from utils.enums import ReminderUrgency, Role
from utils.formatters import format_dt as _format_dt

logger = logging.getLogger(__name__)


async def _send(
    bot: Bot, telegram_id: int | None, text: str, *, reply_markup: InlineKeyboardMarkup | None = None
) -> bool:
    """Bitta xodimga xabar yuboradi. Xato tizimni qulatmaydi — faqat log qiladi."""
    if telegram_id is None:
        return False
    try:
        await bot.send_message(telegram_id, text, reply_markup=reply_markup)
        return True
    except TelegramForbiddenError:
        logger.warning("Xodim botni bloklagan yoki chatni o'chirgan (telegram_id=%s)", telegram_id)
    except TelegramBadRequest as exc:
        logger.warning("Noto'g'ri so'rov, xabar yuborilmadi (telegram_id=%s): %s", telegram_id, exc)
    except TelegramAPIError as exc:
        logger.error("Telegram API xatosi (telegram_id=%s): %s", telegram_id, exc)
    return False


async def notify_task_started(bot: Bot, task_id: int) -> None:
    """7.1-band: vazifa boshlanganda unga biriktirilgan barcha xodimlarga xabar."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_task_started: task %s topilmadi", task_id)
            return

        assignments = await TaskAssignmentRepository(session).list_by_task(task_id)
        employee_repo = EmployeeRepository(session)
        employees = [
            e for e in [await employee_repo.get_by_id(a.employee_id) for a in assignments] if e is not None
        ]

    text = f"🆕 Yangi vazifa: {task.title}\nMuddat: {_format_dt(task.deadline)}"
    if task.trello_card_id:  # MISC vazifada (9-band) Trello karta umuman yo'q
        text += f"\nKarta: {task.trello_card_id}"

    for employee in employees:
        await _send(bot, employee.telegram_id, text)


async def notify_task_stopped(bot: Bot, stop_log_id: int) -> None:
    """7.5-band: "Stop" bosilganda to'xtatgan xodimga, uning brigadiriga va shu
    yo'nalishdagi nazoratchi/adminlarga xabar (`timer_service.stop_task()`
    qaytargan `StopLog.id` asosida)."""
    async with async_session() as session:
        stop_repo = StopLogRepository(session)
        task_repo = TaskRepository(session)
        employee_repo = EmployeeRepository(session)
        brigade_repo = BrigadeRepository(session)

        stop_log = await stop_repo.get_by_id(stop_log_id)
        if stop_log is None:
            logger.warning("notify_task_stopped: stop_log %s topilmadi", stop_log_id)
            return

        task = await task_repo.get_by_id(stop_log.task_id)
        if task is None:
            logger.warning("notify_task_stopped: task %s topilmadi", stop_log.task_id)
            return

        stopper = await employee_repo.get_by_id(stop_log.employee_id)

        recipients: dict[int, int | None] = {}  # employee_id -> telegram_id
        if stopper is not None:
            recipients[stopper.id] = stopper.telegram_id

            if stopper.brigade_id is not None:
                brigade = await brigade_repo.get_by_id(stopper.brigade_id)
                if brigade is not None and brigade.brigadier_id is not None:
                    brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
                    if brigadier is not None:
                        recipients[brigadier.id] = brigadier.telegram_id

        for employee in await employee_repo.list_by_department(task.current_department_id):
            if employee.role in (Role.SUPERVISOR, Role.ADMIN):
                recipients[employee.id] = employee.telegram_id

    text = (
        f"🛑 Vazifa to'xtatildi: {task.title}\n"
        f"Kim to'xtatdi: {stopper.full_name if stopper else 'noma’lum'}\n"
        f"Sabab: {stop_log.reason}\n"
        f"Vaqt: {_format_dt(stop_log.stopped_at)}"
    )
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


async def notify_stage_pending_setup(bot: Bot, task_id: int) -> None:
    """6.1/7.4-band: buyurtma keyingi bo'limga o'tganda (`task_service.advance_task_stage()`)
    chaqiriladi — task hali `PENDING_SETUP` holatida, muddat/xodim yo'q.
    Yangi bo'limning `SUPERVISOR`lariga + BARCHA `ADMIN`larga (nazoratchi hali
    tayinlanmagan holatda ham signal yetib borishi uchun, zaxira sifatida)
    "Sozlash" so'rovi yuboriladi. `handlers/admin/advance_task.py`dagi FSM
    shu xabardagi task_id orqali davom etadi."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_stage_pending_setup: task %s topilmadi", task_id)
            return

        recipients: dict[int, int | None] = {}  # employee_id -> telegram_id
        if task.current_department_id is not None:
            for employee in await EmployeeRepository(session).list_by_department(
                task.current_department_id
            ):
                if employee.role == Role.SUPERVISOR:
                    recipients[employee.id] = employee.telegram_id

        for admin in await EmployeeRepository(session).list_by_role(Role.ADMIN):
            recipients[admin.id] = admin.telegram_id

        department = (
            await DepartmentRepository(session).get_by_id(task.current_department_id)
            if task.current_department_id is not None
            else None
        )

    department_name = department.name if department is not None else "noma'lum bo'lim"
    text = (
        f"⏳ Buyurtma \"{task.title}\" {department_name} bo'limiga keldi.\n"
        f"Muddat va xodim(lar)ni belgilash uchun quyidagi tugmani bosing:"
    )
    keyboard = build_advance_setup_keyboard(task.id)
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text, reply_markup=keyboard)


async def notify_penalty_applied(bot: Bot, kpi_log_id: int) -> None:
    """8-band: ball (jarima/bonus) yozilganda xodimga aniq sabab va miqdor bilan xabar."""
    async with async_session() as session:
        kpi_log = await KpiLogRepository(session).get_by_id(kpi_log_id)
        if kpi_log is None:
            logger.warning("notify_penalty_applied: kpi_log %s topilmadi", kpi_log_id)
            return

        employee = await EmployeeRepository(session).get_by_id(kpi_log.employee_id)
        if employee is None:
            logger.warning("notify_penalty_applied: employee %s topilmadi", kpi_log.employee_id)
            return

    title = "🎁 Sizga bonus ball yozildi" if kpi_log.score > 0 else "⚠️ Sizga jarima ball yozildi"
    text = f"{title}: {kpi_log.score:+d} ball\nSabab: {kpi_log.reason}"
    await _send(bot, employee.telegram_id, text)


_REMINDER_HEADERS = {
    ReminderUrgency.INFO: "⏰ Bugun muddati tugaydigan vazifalaringiz ({n} ta):",
    ReminderUrgency.WARNING: "⚠️ Diqqat, muddat yaqinlashmoqda! Bugungi vazifalaringiz ({n} ta):",
    ReminderUrgency.URGENT: "🚨 Bugun oxirgi muhlat! Vazifalaringiz ({n} ta):",
}


async def notify_daily_reminder(
    bot: Bot, employee_id: int, tasks: list[Task], urgency: ReminderUrgency
) -> bool:
    """7.3-band: kunlik eslatma — bitta xodimga bugun muddati tugaydigan
    vazifalari ro'yxatini yuboradi, kun davomidagi eslatma vaqtiga qarab
    (`urgency`) matn kuchayib boradi. `tasks` chaqiruvchi tomonidan
    tayyorlanadi (`jobs/reminder_job.py`) — bu funksiya faqat
    formatlash+yuborishga javobgar."""
    if not tasks:
        return False

    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        logger.warning("notify_daily_reminder: employee %s topilmadi", employee_id)
        return False

    lines = [_REMINDER_HEADERS[urgency].format(n=len(tasks))]
    for task in tasks:
        lines.append(f"• {task.title} — {_format_dt(task.deadline)}")

    return await _send(bot, employee.telegram_id, "\n".join(lines))


async def _collect_assignees(session, task_id: int) -> dict[int, int | None]:
    """task_id'ga biriktirilgan barcha xodimlar -> telegram_id xaritasi."""
    recipients: dict[int, int | None] = {}
    employee_repo = EmployeeRepository(session)
    for assignment in await TaskAssignmentRepository(session).list_by_task(task_id):
        employee = await employee_repo.get_by_id(assignment.employee_id)
        if employee is not None:
            recipients[employee.id] = employee.telegram_id
    return recipients


async def notify_deadline_approaching(bot: Bot, task_id: int) -> None:
    """7.2-band: "Muddatga 1 kun qoldi" — Xodim(lar), Brigadir, Nazoratchi.
    `overdue_watch_job` faqat bitta marta chaqiradi (`day_left_notified_at`
    orqali qayta yubormaslikni o'zi ta'minlaydi)."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_deadline_approaching: task %s topilmadi", task_id)
            return

        employee_repo = EmployeeRepository(session)
        brigade_repo = BrigadeRepository(session)
        recipients = await _collect_assignees(session, task_id)

        for assignee_id in list(recipients):
            assignee = await employee_repo.get_by_id(assignee_id)
            if assignee is not None and assignee.brigade_id is not None:
                brigade = await brigade_repo.get_by_id(assignee.brigade_id)
                if brigade is not None and brigade.brigadier_id is not None:
                    brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
                    if brigadier is not None:
                        recipients[brigadier.id] = brigadier.telegram_id

        if task.current_department_id is not None:
            for employee in await employee_repo.list_by_department(task.current_department_id):
                if employee.role == Role.SUPERVISOR:
                    recipients[employee.id] = employee.telegram_id

    text = f"⏳ \"{task.title}\" vazifasiga muddatga 1 kun qoldi!\nMuddat: {_format_dt(task.deadline)}"
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


async def notify_task_overdue(bot: Bot, task_id: int) -> None:
    """7.2-band: "Muddat o'tib ketdi" — Xodim(lar), Nazoratchi, Rahbar (ADMIN)."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_task_overdue: task %s topilmadi", task_id)
            return

        employee_repo = EmployeeRepository(session)
        recipients = await _collect_assignees(session, task_id)

        if task.current_department_id is not None:
            for employee in await employee_repo.list_by_department(task.current_department_id):
                if employee.role == Role.SUPERVISOR:
                    recipients[employee.id] = employee.telegram_id

        for admin in await employee_repo.list_by_role(Role.ADMIN):
            recipients[admin.id] = admin.telegram_id

    text = f"🔴 \"{task.title}\" vazifasining muddati o'tib ketdi!\nMuddat: {_format_dt(task.deadline)}"
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


async def notify_reassignment_candidate(bot: Bot, task_id: int) -> None:
    """8.3-band: 48 soatdan ortiq kechikkan buyurtma uchun avtomatik-
    aniqlangan brigadaga-o'tkazish signali — bo'lim NAZORATCHI(lari) + barcha
    ADMIN'larga "Ko'rib chiqish" tugmasi bilan (yakuniy tasdiq qo'lda,
    `handlers/admin/reassign_task.py`)."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_reassignment_candidate: task %s topilmadi", task_id)
            return

        employee_repo = EmployeeRepository(session)
        recipients: dict[int, int | None] = {}

        if task.current_department_id is not None:
            for employee in await employee_repo.list_by_department(task.current_department_id):
                if employee.role == Role.SUPERVISOR:
                    recipients[employee.id] = employee.telegram_id

        for admin in await employee_repo.list_by_role(Role.ADMIN):
            recipients[admin.id] = admin.telegram_id

    text = (
        f"🔁 \"{task.title}\" 48 soatdan ortiq kechikmoqda.\n"
        "Boshqa brigadaga o'tkazishni ko'rib chiqing:"
    )
    keyboard = build_reassign_review_keyboard(task.id)
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text, reply_markup=keyboard)


async def notify_task_reassigned(
    bot: Bot, task_id: int, *, old_employee_ids: list[int], new_employee_ids: list[int]
) -> None:
    """8.3-band: brigadaga o'tkazish yakunlangach — eski brigadaga va yangi
    brigadaga ALOHIDA xabar (`task_service.reassign_task_brigade()` chaqiruvchisi
    tomonidan uzatilgan xodim ID ro'yxatlari asosida, chunki o'tkazishdan keyin
    `task_assignments` allaqachon yangi brigadaga almashtirilgan bo'ladi)."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_task_reassigned: task %s topilmadi", task_id)
            return

        employee_repo = EmployeeRepository(session)
        old_recipients = {
            e.id: e.telegram_id for e in [await employee_repo.get_by_id(i) for i in old_employee_ids] if e is not None
        }
        new_recipients = {
            e.id: e.telegram_id for e in [await employee_repo.get_by_id(i) for i in new_employee_ids] if e is not None
        }

    old_text = f"🔁 \"{task.title}\" boshqa brigadaga o'tkazildi. Sizning brigadangiz ushbu buyurtma bo'yicha jarimalandi."
    new_text = f"🔁 Sizning brigadangizga yangi buyurtma o'tkazildi: \"{task.title}\"\nMuddat: {_format_dt(task.deadline)}"

    for telegram_id in old_recipients.values():
        await _send(bot, telegram_id, old_text)
    for telegram_id in new_recipients.values():
        await _send(bot, telegram_id, new_text)
