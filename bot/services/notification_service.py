"""Telegram bildirishnomalari (3-band: faqat kartaga BELGILANGAN odamlarga signal).

`timer_service`/`penalty_service` singari, DB o'qish o'z sessiyasini ochib-yopadi.
Bu servis yozuv qilmaydi (faqat o'qiydi + xabar yuboradi), shu sababli commit yo'q.
Har bir yuborish `_send()` orqali izolyatsiya qilingan: bitta xodimga xabar
yuborilmay qolishi (masalan, botni bloklagan) qolganlarga ta'sir qilmaydi va
tizimni qulatmaydi.
"""

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

from core.database import async_session
from keyboards.miniapp_kb import build_miniapp_button
from db.models.task import Task
from db.repositories import (
    BrigadeRepository,
    ClientRepository,
    DepartmentRepository,
    EmployeeRepository,
    FinancialSuggestionRepository,
    KpiLogRepository,
    LeadRepository,
    StopLogRepository,
    TaskAssignmentRepository,
    TaskRepository,
)
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

    text = f"🆕 Yangi vazifa: {task.title}\nMuddat: {_format_dt(task.deadline)}\nBatafsil: Mini App'da ko'ring."
    miniapp_button = build_miniapp_button()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[miniapp_button]]) if miniapp_button else None
    for employee in employees:
        await _send(bot, employee.telegram_id, text, reply_markup=keyboard)


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
        f"Muddat va xodim(lar)ni belgilash uchun Mini App'ning \"⏳ Sozlash kutilmoqda\" bo'limini oching."
    )
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


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
        "Boshqa brigadaga o'tkazishni Mini App'ning \"🔁 Ko'rib chiqish kutilmoqda\" bo'limida ko'rib chiqing."
    )
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


async def notify_financial_flag(bot: Bot, suggestion_id: int) -> None:
    """8.6-band 1-qoida: bosqich sozlangan chegaradan ortiq davom etgani
    avtomatik bayroqlanganda — bo'lim NAZORATCHI(lari) + barcha ADMIN'larga
    signal. Summa hali noma'lum (kelajakdagi admin UI keyin to'ldiradi),
    shu sabab xabar faqat bayroqni e'lon qiladi, aniq son bermaydi."""
    async with async_session() as session:
        suggestion = await FinancialSuggestionRepository(session).get_by_id(suggestion_id)
        if suggestion is None:
            logger.warning("notify_financial_flag: suggestion %s topilmadi", suggestion_id)
            return

        task = await TaskRepository(session).get_by_id(suggestion.task_id)
        if task is None:
            logger.warning("notify_financial_flag: task %s topilmadi", suggestion.task_id)
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
        f"💰 \"{task.title}\" bosqichi {suggestion.stage_duration_days} kundan ortiq davom etmoqda "
        "(8.6-band). Mijoz to'lovi ushlanib qolgan bo'lsa, moliyaviy taklifni ko'rib chiqing."
    )
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


async def notify_admins_report(bot: Bot, text: str) -> None:
    """10.2-band: `jobs/report_job.py`ning kunlik/haftalik/oylik hisobotlari
    barcha ADMIN+SUPERVISOR'larga shu orqali yuboriladi (Markdown kod-blok
    matni — `stats_service.format_stats_table()` chiqarishi)."""
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        recipients: dict[int, int | None] = {}
        for role in (Role.ADMIN, Role.SUPERVISOR):
            for employee in await employee_repo.list_by_role(role):
                recipients[employee.id] = employee.telegram_id

    for telegram_id in recipients.values():
        if telegram_id is None:
            continue
        try:
            await bot.send_message(telegram_id, text, parse_mode="Markdown")
        except (TelegramForbiddenError, TelegramBadRequest, TelegramAPIError):
            logger.warning("notify_admins_report: xabar yetmadi (telegram_id=%s)", telegram_id)


async def notify_client_stage_advanced(bot: Bot, task_id: int) -> None:
    """12-band: "Mahsulot qaysidir bo'limdan CHIQQANDA mijozga xabar boradi."
    `task_id` — endigina yakunlangan bosqich-qator (`task_service.
    advance_task_stage()` chaqiruvchisi tomonidan, karta hali arxivlanmagan
    holatda). Mijoz bog'lanmagan (`client_id IS NULL`) yoki Telegram'ga hali
    ulanmagan (`telegram_id IS NULL`) bo'lsa — jim o'tkazib yuboriladi."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None or task.client_id is None:
            return

        client = await ClientRepository(session).get_by_id(task.client_id)
        if client is None or client.telegram_id is None:
            return

        department = (
            await DepartmentRepository(session).get_by_id(task.current_department_id)
            if task.current_department_id is not None
            else None
        )

    department_name = department.name if department is not None else "joriy bosqich"
    text = f"📦 Buyurtmangiz \"{task.title}\" {department_name} bosqichidan o'tdi."
    await _send(bot, client.telegram_id, text)


async def notify_client_task_stopped(bot: Bot, stop_log_id: int) -> None:
    """12-band: "'Stop' bosilganda ham mijozga avtomatik xabarnoma yuboriladi."
    `notify_task_stopped` bilan bir xil `stop_log_id`dan chaqiriladi."""
    async with async_session() as session:
        stop_log = await StopLogRepository(session).get_by_id(stop_log_id)
        if stop_log is None:
            return

        task = await TaskRepository(session).get_by_id(stop_log.task_id)
        if task is None or task.client_id is None:
            return

        client = await ClientRepository(session).get_by_id(task.client_id)
        if client is None or client.telegram_id is None:
            return

    text = f"⏸ Buyurtmangiz \"{task.title}\" vaqtincha to'xtatildi.\nSabab: {stop_log.reason}"
    await _send(bot, client.telegram_id, text)


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


async def notify_lead_follow_up(bot: Bot, lead_id: int) -> None:
    """13.3-band: mas'ul sotuvchiga "uzoq aloqasiz lid" eslatmasi
    (`jobs/lead_follow_up_job.py`, kunlik — chegaradan ortiq turgan har
    kuni qayta yuboriladi, TZ "avtomatik eslatma bo'lib boradi" iborasi
    bir martalik emas, davomiy signalni nazarda tutadi)."""
    async with async_session() as session:
        lead = await LeadRepository(session).get_by_id(lead_id)
        if lead is None:
            logger.warning("notify_lead_follow_up: lead %s topilmadi", lead_id)
            return

        client = await ClientRepository(session).get_by_id(lead.client_id)
        seller = await EmployeeRepository(session).get_by_id(lead.assigned_seller_id)
        if seller is None:
            return

    client_name = client.full_name if client else "noma'lum mijoz"
    days_idle = (datetime.now(timezone.utc) - lead.last_contacted_at).days
    text = f"📞 \"{client_name}\" bilan {days_idle} kundan beri aloqa yo'q. Qo'ng'iroq qiling."
    await _send(bot, seller.telegram_id, text)
