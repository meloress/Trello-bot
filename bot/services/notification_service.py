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

# Uchta claim xabari (yuborildi/tasdiqlandi/rad etildi) shu yagona jadvaldan
# o'qiydi — ilgari har biri o'z ternary'sini yozardi, ya'ni uchinchi amal
# (RESUME) qo'shilishi bilan hammasi "Yakunlash" deb ko'rsatar edi.
CLAIM_ACTION_LABELS = {
    ClaimActionType.PAUSE: "Pauza",
    ClaimActionType.FINISH: "Yakunlash",
    ClaimActionType.RESUME: "Davom ettirish",
}


async def _department_name(session, department_id: int | None) -> str | None:
    """Xabar matniga qo'shiladigan bo'lim nomi — bitta odam bir nechta
    brigadaga rahbarlik qilganda xabar qaysi bo'lim haqida ekani ko'rinishi
    uchun (masalan Kraska va Shkurka)."""
    if department_id is None:
        return None
    department = await DepartmentRepository(session).get_by_id(department_id)
    return department.name if department is not None else None


async def _is_mebel(session, department_id: int | None) -> bool:
    """Mebel moduli ("Fasad seh") MUZLATILGAN — SPEC.md kiritgan yangi
    xabarnoma kanallari (sex guruhi, rahbar zanjiri) unga umuman
    qo'llanmaydi. Ustunlarni bo'sh qoldirish yetarli emas: admin Mini
    App'dan mebel bo'limiga guruh ID yoki mebel xodimiga rahbar yozib
    qo'ysa, muzlatilgan modulning xabar oqimi jimgina o'zgarib ketardi.
    Shu sabab tekshiruv ma'lumotda emas, KODDA."""
    if department_id is None:
        return False
    department = await DepartmentRepository(session).get_by_id(department_id)
    return department is not None and department.module == "mebel"


async def _department_chat_id(session, department_id: int | None) -> str | None:
    """SPEC.md §8: "har sexning o'z Telegram guruhi bor" —
    `departments.telegram_chat_id`. NULL = guruh sozlanmagan, guruhga
    hech narsa yuborilmaydi (xato emas, standart holat). Mebel bo'limlari
    uchun har doim `None` (`_is_mebel` izohiga qarang)."""
    if department_id is None:
        return None
    department = await DepartmentRepository(session).get_by_id(department_id)
    if department is None or department.module == "mebel":
        return None
    return department.telegram_chat_id


async def _add_managers(session, recipients: dict, department_id: int | None) -> None:
    """SPEC.md §7/§8: "rahbar (`user.manager_id`) ham xabarnomaga ulanadi".
    Mavjud qabul qiluvchilarning bevosita rahbarlarini qo'shadi. Mebel
    vazifasi bo'lsa hech narsa qilmaydi (`_is_mebel` izohiga qarang).

    ponytail: bitta pog'ona — rahbarning rahbari qo'shilmaydi. Butun
    ierarxiya kerak bo'lsa shu yerda tsiklga aylantiriladi (halqadan
    himoya bilan); hozircha tashkilotda ikki pog'ona bor."""
    if await _is_mebel(session, department_id):
        return
    employee_repo = EmployeeRepository(session)
    for employee_id in list(recipients):
        employee = await employee_repo.get_by_id(employee_id)
        if employee is None or employee.manager_id is None:
            continue
        manager = await employee_repo.get_by_id(employee.manager_id)
        if manager is not None:
            recipients.setdefault(manager.id, manager.telegram_id)


# TZ 5.6-band: bir xil xodim haqida adminlarga qayta-qayta signal
# yubormaslik uchun — jarayon ichidagi to'plam.
# ponytail: xotirada, bot qayta ishga tushsa tozalanadi (ya'ni signal bir
# marta takrorlanadi — bu zarar emas, aksincha eslatma). Doimiy hisob va
# "necha kundan beri bloklangan" kerak bo'lsa, `employees`ga
# `notifications_blocked_at` ustuni qo'shiladi.
_blocked_reported: set[int] = set()


async def _report_blocked(bot: Bot, telegram_id: int | str) -> None:
    """TZ 5.6-band: "xabarnomani foydalanuvchi o'chira olmasligi kerak".

    Telegram'da buni MAJBURLAB bo'lmaydi — har qanday foydalanuvchi chatni
    "mute" qilishi yoki botni bloklashi mumkin, va Bot API bu holatni
    so'rash imkonini bermaydi. Majburlab bo'lmaydigan narsani KO'RINADIGAN
    qilamiz: bloklash `TelegramForbiddenError` orqali BILINADI, shuning
    uchun bunday xodim aniqlanib, bevosita rahbariga va barcha ADMIN'larga
    signal yuboriladi. Ya'ni "jimgina o'chirib qo'yish" imkoni yo'qoladi —
    ilgari bu holat faqat log faylida qolib ketardi, hech kim ko'rmasdi.

    (Mute'ni — ovozsiz rejimni — bot umuman ko'ra olmaydi; unga qarshi
    yagona chora tashkiliy, texnik emas.)"""
    try:
        employee_telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        return  # sex guruhi yoki noma'lum chat — xodim emas
    if employee_telegram_id in _blocked_reported:
        return

    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        employee = await employee_repo.get_by_telegram_id(employee_telegram_id)
        if employee is None:
            return
        # Mebel ("Fasad seh") MUZLATILGAN: TZ 5.6 — Nazorat Trello talabi, va
        # bu yangi xabar kanali. Mebel adminlariga ilgari bo'lmagan xabar
        # yuborish — o'sha modulning xatti-harakatini o'zgartirish demak.
        # Xodimning O'Z bo'limi tekshiriladi (`notify_penalty_applied` bilan
        # bir xil naqsh) — bu yerda vazifa/bo'lim konteksti yo'q.
        if await _is_mebel(session, employee.department_id):
            return
        recipients: dict[int, int | None] = {}
        if employee.manager_id is not None:
            manager = await employee_repo.get_by_id(employee.manager_id)
            if manager is not None:
                recipients[manager.id] = manager.telegram_id
        for admin in await employee_repo.list_by_role(Role.ADMIN):
            recipients[admin.id] = admin.telegram_id
        recipients.pop(employee.id, None)  # bloklagan odamning o'ziga yubormaymiz

    _blocked_reported.add(employee_telegram_id)
    text = (
        f"🔕 {employee.full_name} botni bloklagan yoki chatni o'chirgan — "
        "unga tizim xabarnomalari (vazifa, muddat, jarima) YETIB BORMAYAPTI.\n"
        "Iltimos, botni qayta ishga tushirishini so'rang."
    )
    for admin_telegram_id in recipients.values():
        # `report_block=False`: adminning o'zi ham bloklagan bo'lsa, cheksiz
        # rekursiya boshlanib ketmasligi uchun.
        await _send(bot, admin_telegram_id, text, report_block=False)


async def _send(
    bot: Bot,
    telegram_id: int | str | None,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    report_block: bool = True,
) -> bool:
    """Bitta chatga (xodim yoki sex guruhi) xabar yuboradi. Xato tizimni
    qulatmaydi — faqat log qiladi.

    `report_block=False` — faqat `_report_blocked()` ichidan, rekursiyani
    to'xtatish uchun."""
    if telegram_id is None:
        return False
    try:
        await bot.send_message(telegram_id, text, reply_markup=reply_markup)
        return True
    except TelegramForbiddenError:
        logger.warning("Xodim botni bloklagan yoki chatni o'chirgan (telegram_id=%s)", telegram_id)
        if report_block:
            try:
                await _report_blocked(bot, telegram_id)
            except Exception:
                logger.exception("_report_blocked xatosi (telegram_id=%s)", telegram_id)
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
        department_name = await _department_name(session, task.current_department_id)
        group_chat_id = await _department_chat_id(session, task.current_department_id)

        # TZ 5.2-band: "xodimning RAHBARIGA ham xabar dublikat qilinadi".
        # Ilgari bu kanal faqat "muddat o'tdi" va "jarima yozildi" hodisalarida
        # ulangan edi — TZ esa aynan yangi vazifa biriktirilishini nazarda
        # tutadi. Ijrochilarning o'zi `recipients`dan ayriladi (ular asosiy
        # matnni allaqachon oladi), rahbarga esa boshqa ohangdagi xabar ketadi.
        assignee_ids = {e.id for e in employees}
        with_managers = {e.id: e.telegram_id for e in employees}
        await _add_managers(session, with_managers, task.current_department_id)
        manager_chat_ids = [
            telegram_id
            for employee_id, telegram_id in with_managers.items()
            if employee_id not in assignee_ids
        ]

    department_line = f"\nBo'lim: {department_name}" if department_name else ""
    text = (
        f"🆕 Yangi vazifa: {task.title}{department_line}\n"
        f"Muddat: {_format_dt(task.deadline)}\nBatafsil: Mini App'da ko'ring."
    )
    assignee_names = ", ".join(e.full_name for e in employees) or "—"
    miniapp_button = build_miniapp_button()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[miniapp_button]]) if miniapp_button else None
    for employee in employees:
        await _send(bot, employee.telegram_id, text, reply_markup=keyboard)

    for telegram_id in manager_chat_ids:
        await _send(bot, telegram_id, f"👤 Bo'ysunuvchingiz {assignee_names}ga vazifa berildi.\n{text}")

    # SPEC.md §8: "Yangi vazifa biriktirildi -> Mas'ul (shaxsiy) + sex guruhi".
    # Guruhga Mini App tugmasi qo'yilmaydi — `web_app` tugmasi faqat shaxsiy
    # chatda ochiladi, guruhda Telegram uni umuman ko'rsatmaydi.
    if group_chat_id:
        await _send(bot, group_chat_id, f"{text}\nMas'ul: {assignee_names}")


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
        department_name = await _department_name(session, task.current_department_id)

    department_prefix = f"{department_name}: " if department_name else ""
    text = f"✅ {department_prefix}\"{task.title}\" Trello orqali {assignee_name}ga topshirildi."
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

        # TZ 5.4-band: "Stop" ham sex guruhiga chiqadi — ilgari guruh kanali
        # faqat "yangi vazifa" va "muddat o'tdi"da ishlatilardi, holbuki
        # to'xtash aynan butun sex ko'rishi kerak bo'lgan hodisa. Mebel uchun
        # `_department_chat_id()` har doim None qaytaradi (muzlatilgan modul).
        group_chat_id = await _department_chat_id(session, task.current_department_id)

    text = (
        f"🛑 Vazifa to'xtatildi: {task.title}\n"
        f"Kim to'xtatdi: {stopper.full_name if stopper else 'noma’lum'}\n"
        f"Sabab: {stop_log.reason}\n"
        f"Vaqt: {_format_dt(stop_log.stopped_at)}"
    )
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)
    if group_chat_id:
        await _send(bot, group_chat_id, text)


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

        employee_repo = EmployeeRepository(session)
        employee = await employee_repo.get_by_id(kpi_log.employee_id)
        if employee is None:
            logger.warning("notify_penalty_applied: employee %s topilmadi", kpi_log.employee_id)
            return

        # SPEC.md §7: "rahbar ham xabarnomaga ulanishi mumkin". Faqat JARIMA
        # (manfiy ball) — bonus xodimning o'z ishi, rahbarni har musbat ball
        # bilan bezovta qilishning ma'nosi yo'q. Mebel xodimlari uchun bu
        # kanal umuman yo'q (`_is_mebel` izohiga qarang) — bu yerda xodimning
        # O'Z bo'limi tekshiriladi, chunki KPI yozuvida vazifa/bo'lim yo'q.
        manager = None
        if (
            kpi_log.score < 0
            and employee.manager_id is not None
            and not await _is_mebel(session, employee.department_id)
        ):
            manager = await employee_repo.get_by_id(employee.manager_id)

    title = "🎁 Sizga bonus ball yozildi" if kpi_log.score > 0 else "⚠️ Sizga jarima ball yozildi"
    text = f"{title}: {kpi_log.score:+d} ball\nSabab: {kpi_log.reason}"
    await _send(bot, employee.telegram_id, text)
    if manager is not None:
        await _send(
            bot,
            manager.telegram_id,
            f"⚠️ Bo'ysunuvchingiz {employee.full_name}ga jarima ball yozildi: "
            f"{kpi_log.score:+d}\nSabab: {kpi_log.reason}",
        )


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


async def notify_deadline_changed(bot: Bot, task_id: int, *, old_deadline) -> None:
    """TZ 2.3-band: muddat QO'LDA o'zgartirilganda ijrochi(lar), brigadir va
    bo'lim nazoratchisiga xabar. Muddat KPI ballining bazasi — ishchi
    o'zgarishni bilmasa, u bilmagan muddat uchun jarima olishi mumkin edi."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            logger.warning("notify_deadline_changed: task %s topilmadi", task_id)
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

    old_line = f"\nOldingi muddat: {_format_dt(old_deadline)}" if old_deadline else ""
    text = (
        f"📅 \"{task.title}\" vazifasining muddati o'zgartirildi.\n"
        f"Yangi muddat: {_format_dt(task.deadline)}{old_line}"
    )
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

        # SPEC.md §8: "Muddat o'tdi -> Mas'ul + rahbar + sex guruhi".
        await _add_managers(session, recipients, task.current_department_id)
        group_chat_id = await _department_chat_id(session, task.current_department_id)

    text = f"🔴 \"{task.title}\" vazifasining muddati o'tib ketdi!\nMuddat: {_format_dt(task.deadline)}"
    for telegram_id in recipients.values():
        await _send(bot, telegram_id, text)
    if group_chat_id:
        await _send(bot, group_chat_id, text)


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

        department_name = await _department_name(session, task.current_department_id)

    action_label = CLAIM_ACTION_LABELS[claim.action_type]
    claimant_name = claimant.full_name if claimant is not None else "noma'lum xodim"
    reason_line = f"\nSabab: {claim.reason}" if claim.reason else ""
    department_prefix = f"{department_name}: " if department_name else ""
    text = (
        f"📋 {department_prefix}{claimant_name} \"{task.title}\" bo'yicha {action_label} so'rovini yubordi.\n"
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
        department_name = await _department_name(session, task.current_department_id)

    action_label = CLAIM_ACTION_LABELS[claim.action_type]
    department_prefix = f"{department_name}: " if department_name else ""
    text = f"✅ \"{task.title}\" bo'yicha {action_label} so'rovingiz tasdiqlandi."
    await _send(bot, employee.telegram_id, text)
    if brigadier_telegram_id is not None and brigadier_telegram_id != employee.telegram_id:
        await _send(
            bot,
            brigadier_telegram_id,
            f"✅ {department_prefix}{employee.full_name}: \"{task.title}\" bo'yicha {action_label} so'rovi tasdiqlandi.",
        )


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
        department_name = await _department_name(session, task.current_department_id)

    action_label = CLAIM_ACTION_LABELS[claim.action_type]
    department_prefix = f"{department_name}: " if department_name else ""
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
            f"❌ {department_prefix}{employee.full_name}: \"{task.title}\" bo'yicha {action_label} so'rovi rad etildi.{note_line}\n"
            "Vazifa avvalgidek davom etmoqda.",
        )




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
