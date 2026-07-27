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
    KpiLogRepository,
    LeadRepository,
    StopLogRepository,
    TaskAssignmentRepository,
    TaskClaimRepository,
    TaskRepository,
    TaskSellerRepository,
)
from utils.enums import ClaimActionType, ReminderUrgency, Role
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


async def notify_task_delegated_via_trello(bot: Bot, task_id: int, brigadier_id: int) -> None:
    """Mebel moduli: brigadir ishchini Trello kartaga a'zo qilib qo'shganda
    (`jobs/trello_ingest_job.py`ning `_handle_open_task` a'zo-o'zgarishi
    aniqlashi orqali) — ishga endi biriktirilgan ishchiga `notify_task_started`
    alohida yuboriladi (chaqiruvchi tarafda), bu funksiya esa faqat
    BRIGADIRga o'z Trello amali qabul qilinganini tasdiqlaydi."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        brigadier = await EmployeeRepository(session).get_by_id(brigadier_id)
    if task is None or brigadier is None or brigadier.telegram_id is None:
        return

    assignee_name = "—"
    async with async_session() as session:
        assignments = await TaskAssignmentRepository(session).list_by_task(task_id)
        employee_repo = EmployeeRepository(session)
        for assignment in assignments:
            employee = await employee_repo.get_by_id(assignment.employee_id)
            if employee is not None:
                assignee_name = employee.full_name
                break

    text = f"✅ \"{task.title}\" Trello orqali {assignee_name}ga topshirildi."
    await _send(bot, brigadier.telegram_id, text)


async def notify_task_stopped(bot: Bot, stop_log_id: int) -> None:
    """7.5-band: "Stop" bosilganda to'xtatgan xodimga, uning brigadiriga, shu
    yo'nalishdagi nazoratchi/adminlarga VA buyurtmaga biriktirilgan barcha
    sotuvchilarga (Fasad sex TZ Phase 5) xabar (`timer_service.stop_task()`
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

        # Fasad sex TZ Phase 5: buyurtmaga biriktirilgan sotuvchi(lar) ham
        # Stop haqida xabar olishi kerak. `recipients` employee_id bo'yicha
        # kalitlangani uchun bir kishi ham supervisor/admin, ham sotuvchi
        # bo'lsa avtomatik deduplikatsiya qilinadi (ikki marta yubormaydi).
        for task_seller in await TaskSellerRepository(session).list_by_task(task.id):
            seller = await employee_repo.get_by_id(task_seller.employee_id)
            if seller is not None:
                recipients[seller.id] = seller.telegram_id

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


async def notify_daily_report_request(bot: Bot, employee_id: int) -> bool:
    """Fasad sex TZ, Phase 8: kunlik rasm/video hisobot SO'ROVI — oddiy
    matnli xabar (state o'rnatilmaydi, tugma biriktirilmaydi; xodim
    javoban rasm/video yuborsa `handlers/common/daily_report.py`ning
    state'siz filteri uni ushlaydi — sabab shu faylning docstring'ida)."""
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        logger.warning("notify_daily_report_request: employee %s topilmadi", employee_id)
        return False

    return await _send(
        bot, employee.telegram_id, "📸 Bugungi ish jarayoni bo'yicha rasm yoki video yuboring."
    )


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


async def notify_claim_submitted(bot: Bot, claim_id: int) -> None:
    """Mebel moduli: ishchi Mini App'da Pauza/Yakunlash bosganda — uning
    brigadiriga (faqat ma'lumot uchun, tasdiqlash tugmasisiz) va bo'lim
    rahbari (SUPERVISOR) + barcha ADMIN'larga (tasdiqlash chaqirig'i bilan)
    xabar boradi. Faqat rahbar/admin tasdiqlay oladi — brigadir shu xabarni
    ko'radi, lekin `miniapp/api/brigadier.py`da tasdiqlash endpoint'i yo'q."""
    async with async_session() as session:
        claim = await TaskClaimRepository(session).get_by_id(claim_id)
        if claim is None:
            logger.warning("notify_claim_submitted: claim %s topilmadi", claim_id)
            return

        task = await TaskRepository(session).get_by_id(claim.task_id)
        if task is None:
            logger.warning("notify_claim_submitted: task %s topilmadi", claim.task_id)
            return

        employee_repo = EmployeeRepository(session)
        claimant = await employee_repo.get_by_id(claim.employee_id)

        recipients: dict[int, int | None] = {}
        if claimant is not None and claimant.brigade_id is not None:
            brigade = await BrigadeRepository(session).get_by_id(claimant.brigade_id)
            if brigade is not None and brigade.brigadier_id is not None:
                brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
                if brigadier is not None:
                    recipients[brigadier.id] = brigadier.telegram_id

        if task.current_department_id is not None:
            for employee in await employee_repo.list_by_department(task.current_department_id):
                if employee.role == Role.SUPERVISOR:
                    recipients[employee.id] = employee.telegram_id
        for admin in await employee_repo.list_by_role(Role.ADMIN):
            recipients[admin.id] = admin.telegram_id

    action_label = "Pauza" if claim.action_type == ClaimActionType.PAUSE else "Yakunlash"
    claimant_name = claimant.full_name if claimant is not None else "noma'lum xodim"
    reason_line = f"\nSabab: {claim.reason}" if claim.reason else ""
    text = (
        f"📋 {claimant_name} \"{task.title}\" bo'yicha {action_label} so'rovini yubordi.\n"
        f"Vaqt: {_format_dt(claim.claimed_at)}{reason_line}\n"
        "Tasdiqlash: Mini App → \"Tasdiqlash kutilmoqda\"."
    )
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


async def _claimant_brigadier_telegram_id(session, claimant) -> int | None:
    """Mebel moduli: Pauza/Yakunlash mebel'da brigadir tomonidan a'zo nomidan
    yuboriladi (`miniapp/api/brigadier.py`), shu sabab tasdiqlash/rad etish
    natijasi ham brigadirga qaytishi kerak — u ish holatini bilib, kerak
    bo'lsa davom ettirish tugmasini bosadi."""
    if claimant is None or claimant.brigade_id is None:
        return None
    brigade = await BrigadeRepository(session).get_by_id(claimant.brigade_id)
    if brigade is None or brigade.brigadier_id is None:
        return None
    brigadier = await EmployeeRepository(session).get_by_id(brigade.brigadier_id)
    return brigadier.telegram_id if brigadier is not None else None


async def notify_claim_approved(bot: Bot, claim_id: int) -> None:
    """Mebel moduli: rahbar so'rovni tasdiqlagach — so'rov egasi (ishchi) va
    uning brigadiriga (brigadir bu amalni ishchi nomidan yuborgan, natijani
    bilishi shart)."""
    async with async_session() as session:
        claim = await TaskClaimRepository(session).get_by_id(claim_id)
        if claim is None:
            logger.warning("notify_claim_approved: claim %s topilmadi", claim_id)
            return
        task = await TaskRepository(session).get_by_id(claim.task_id)
        employee = await EmployeeRepository(session).get_by_id(claim.employee_id)
        if task is None or employee is None:
            return
        brigadier_telegram_id = await _claimant_brigadier_telegram_id(session, employee)

    action_label = "Pauza" if claim.action_type == ClaimActionType.PAUSE else "Yakunlash"
    text = f"✅ \"{task.title}\" bo'yicha {action_label} so'rovingiz tasdiqlandi."
    await _send(bot, employee.telegram_id, text)
    if brigadier_telegram_id is not None and brigadier_telegram_id != employee.telegram_id:
        await _send(bot, brigadier_telegram_id, f"✅ {employee.full_name}: \"{task.title}\" bo'yicha {action_label} so'rovi tasdiqlandi.")


async def notify_claim_rejected(bot: Bot, claim_id: int) -> None:
    """Mebel moduli: rahbar so'rovni rad etgach — so'rov egasi (ishchi) va
    uning brigadiriga, vazifa avvalgidek davom etayotganini bildirib (hech
    qanday holat o'zgarmagan, `claim_service.reject_claim()`ga qarang)."""
    async with async_session() as session:
        claim = await TaskClaimRepository(session).get_by_id(claim_id)
        if claim is None:
            logger.warning("notify_claim_rejected: claim %s topilmadi", claim_id)
            return
        task = await TaskRepository(session).get_by_id(claim.task_id)
        employee = await EmployeeRepository(session).get_by_id(claim.employee_id)
        if task is None or employee is None:
            return
        brigadier_telegram_id = await _claimant_brigadier_telegram_id(session, employee)

    action_label = "Pauza" if claim.action_type == ClaimActionType.PAUSE else "Yakunlash"
    note_line = f"\nSabab: {claim.rejection_note}" if claim.rejection_note else ""
    text = (
        f"❌ \"{task.title}\" bo'yicha {action_label} so'rovingiz rad etildi.{note_line}\n"
        "Vazifa avvalgidek davom etmoqda."
    )
    await _send(bot, employee.telegram_id, text)
    if brigadier_telegram_id is not None and brigadier_telegram_id != employee.telegram_id:
        await _send(
            bot,
            brigadier_telegram_id,
            f"❌ {employee.full_name}: \"{task.title}\" bo'yicha {action_label} so'rovi rad etildi.{note_line}\n"
            "Vazifa avvalgidek davom etmoqda.",
        )


async def notify_task_resumed(bot: Bot, task_id: int, employee_id: int) -> None:
    """Mebel moduli: brigadir a'zoning to'xtatilgan (STOPPED) vazifasini
    davom ettirgach — `resume` claim-gated emas (rahbar tasdig'i shart
    emas), shu sabab bu shunchaki xabar: bo'lim rahbari (SUPERVISOR) + barcha
    ADMIN'larga."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_task_resumed: task %s topilmadi", task_id)
            return
        employee = await EmployeeRepository(session).get_by_id(employee_id)
        if employee is None:
            return

        employee_repo = EmployeeRepository(session)
        recipients: dict[int, int | None] = {}
        if task.current_department_id is not None:
            for supervisor in await employee_repo.list_by_department(task.current_department_id):
                if supervisor.role == Role.SUPERVISOR:
                    recipients[supervisor.id] = supervisor.telegram_id
        for admin in await employee_repo.list_by_role(Role.ADMIN):
            recipients[admin.id] = admin.telegram_id

    text = f"▶️ {employee.full_name}: \"{task.title}\" bo'yicha ish davom ettirilmoqda."
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


_CLAIM_REMINDER_TEXTS = {
    1: "⏰ Eslatma: \"{title}\" bo'yicha so'rov hali ko'rib chiqilmagan.",
    2: "⚠️ DIQQAT: \"{title}\" bo'yicha so'rov {hours} soatdan beri kutmoqda — iltimos hoziroq ko'rib chiqing.",
    3: "🔴 QAT'IY OGOHLANTIRISH: \"{title}\" bo'yicha so'rov {hours} soatdan beri tasdiqlanmagan — zudlik bilan hal qiling.",
}


async def notify_claim_reminder(bot: Bot, claim_id: int, stage: int) -> None:
    """Mebel moduli: `jobs/overdue_watch_job.py`ning eskalatsiya bosqichi
    (+2/+6/+24 soat, keyingi vazifada qo'shiladi) — bo'lim rahbari
    (SUPERVISOR) + barcha ADMIN + claiming xodimning brigadiriga, `stage`ga
    qarab kuchayib boruvchi ohangda. Noma'lum `stage` qiymati uchun jim
    o'tkazib yuboriladi (chaqiruvchi xato qilgan bo'lishi mumkin, lekin bu
    funksiya o'zi yiqilmasligi kerak)."""
    async with async_session() as session:
        claim = await TaskClaimRepository(session).get_by_id(claim_id)
        if claim is None:
            logger.warning("notify_claim_reminder: claim %s topilmadi", claim_id)
            return
        task = await TaskRepository(session).get_by_id(claim.task_id)
        if task is None:
            logger.warning("notify_claim_reminder: task %s topilmadi", claim.task_id)
            return

        employee_repo = EmployeeRepository(session)
        claimant = await employee_repo.get_by_id(claim.employee_id)

        recipients: dict[int, int | None] = {}
        if claimant is not None and claimant.brigade_id is not None:
            brigade = await BrigadeRepository(session).get_by_id(claimant.brigade_id)
            if brigade is not None and brigade.brigadier_id is not None:
                brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
                if brigadier is not None:
                    recipients[brigadier.id] = brigadier.telegram_id

        if task.current_department_id is not None:
            for employee in await employee_repo.list_by_department(task.current_department_id):
                if employee.role == Role.SUPERVISOR:
                    recipients[employee.id] = employee.telegram_id
        for admin in await employee_repo.list_by_role(Role.ADMIN):
            recipients[admin.id] = admin.telegram_id

    template = _CLAIM_REMINDER_TEXTS.get(stage)
    if template is None:
        logger.warning("notify_claim_reminder: noma'lum bosqich %s (claim_id=%s)", stage, claim_id)
        return

    hours = int((datetime.now(timezone.utc) - claim.claimed_at).total_seconds() // 3600)
    text = template.format(title=task.title, hours=hours)
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)


async def notify_reconciliation_needed(bot: Bot, task_id: int) -> None:
    """Mebel moduli: `jobs/trello_ingest_job.py` kartani keyingi bo'limga
    ko'chirilganini aniqlaganda, lekin eski bosqich hali COMPLETED
    bo'lmasa (masalan ishchi hali "Yakunlash" tugmasini bosmagan yoki
    bosgan-u lekin rahbar hali tasdiqlamagan) — bir martalik xabar
    (`tasks.advanced_without_finish_claim_at` shu chaqiruv bilan bir vaqtda
    birinchi marta belgilanganda, chaqiruvchida)."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_reconciliation_needed: task %s topilmadi", task_id)
            return

        employee_repo = EmployeeRepository(session)
        recipients = await _collect_assignees(session, task_id)

        for assignee_id in list(recipients):
            assignee = await employee_repo.get_by_id(assignee_id)
            if assignee is not None and assignee.brigade_id is not None:
                brigade = await BrigadeRepository(session).get_by_id(assignee.brigade_id)
                if brigade is not None and brigade.brigadier_id is not None:
                    brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
                    if brigadier is not None:
                        recipients[brigadier.id] = brigadier.telegram_id

        if task.current_department_id is not None:
            for employee in await employee_repo.list_by_department(task.current_department_id):
                if employee.role == Role.SUPERVISOR:
                    recipients[employee.id] = employee.telegram_id
        for admin in await employee_repo.list_by_role(Role.ADMIN):
            recipients[admin.id] = admin.telegram_id

    text = (
        f"⚠️ \"{task.title}\" kartasi keyingi bo'limga ko'chirildi, lekin oldingi bosqich "
        "hali \"Yakunlash\" tasdig'idan o'tmagan. Iltimos qo'lda tekshiring."
    )
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)
