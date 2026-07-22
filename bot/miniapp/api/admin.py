"""Rahbar/Nazoratchi ekranlari: dashboard, yangi vazifa, xodimlar, moliyaviy
takliflar. Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR (`server.py`da
route bo'yicha `require_roles` orqali ulanadi)."""

import logging
from datetime import datetime

from aiohttp import web

from core.database import async_session
from db.repositories import (
    BrigadeRepository,
    DepartmentRepository,
    EmployeeRepository,
    FinancialSuggestionRepository,
    TaskAssignmentRepository,
    TaskRepository,
)
from config import settings
from jobs import reminder_job, report_job
from miniapp.util import err
from services import (
    client_service,
    employee_service,
    financial_service,
    notification_service,
    settings_service,
    stats_service,
    task_service,
)
from trello.client import TrelloAPIError, TrelloClient
from utils.enums import Role, TaskStatus
from utils.formatters import ROLE_LABELS

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


async def _active_brigadier_ids(session, brigades) -> set[int]:
    """`GET /departments/{id}/brigadiers` faqat FAOL brigadirlarni
    ro'yxatga chiqaradi — vazifa tayinlashni tekshiruvchi validatsiya ham
    shu bilan bir xil bo'lishi kerak, aks holda deaktivlashtirilgan
    brigadirga (masalan eskirgan frontend keshi orqali) baribir vazifa
    berib qo'yish mumkin bo'lardi."""
    employee_repo = EmployeeRepository(session)
    ids: set[int] = set()
    for brigade in brigades:
        if brigade.brigadier_id is None:
            continue
        brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
        if brigadier is not None and brigadier.is_active:
            ids.add(brigadier.id)
    return ids


@routes.get("/dashboard")
async def dashboard(request: web.Request) -> web.Response:
    stats = await stats_service.get_monthly_stats()
    active_employees = len(stats)
    completed_total = sum(s.completed_tasks for s in stats)
    # O'rtacha ball/yetakchi faqat KPI oladigan rollardan (rahbar/nazoratchi/
    # sotuvchida ball yo'q — aralashtirilsa o'rtacha sun'iy pasayadi).
    kpi_stats = [s for s in stats if s.role in stats_service.KPI_ROLES]
    avg_score = round(sum(s.total_score for s in kpi_stats) / len(kpi_stats)) if kpi_stats else 0
    top = max(kpi_stats, key=lambda s: s.total_score, default=None)

    async with async_session() as session:
        pending_financial = len(await FinancialSuggestionRepository(session).list_pending())

    return web.json_response(
        {
            "active_employees": active_employees,
            "completed_this_month": completed_total,
            "avg_score": avg_score,
            "top_performer": top.full_name if top and top.total_score > 0 else None,
            "pending_financial": pending_financial,
        }
    )


@routes.get("/departments")
async def list_departments(request: web.Request) -> web.Response:
    async with async_session() as session:
        departments = await DepartmentRepository(session).list_all()
    return web.json_response(
        [
            {
                "id": d.id,
                "name": d.name,
                "next_department_id": d.next_department_id,
                "auto_reassign_after_48h": d.auto_reassign_after_48h,
            }
            for d in departments
        ]
    )


@routes.post("/departments/{department_id}/chain")
async def set_department_chain(request: web.Request) -> web.Response:
    """6.1/7.4-band: bo'limning KEYINGI bosqichini sozlash (`/deptchain` bilan
    bir xil mantiq — to'g'ridan-to'g'ri repository orqali, chat handleri ham
    shunday qiladi)."""
    department_id = int(request.match_info["department_id"])
    body = await request.json()
    next_department_id = body.get("next_department_id")

    async with async_session() as session:
        repo = DepartmentRepository(session)
        department = await repo.get_by_id(department_id)
        if department is None:
            return err("not_found", 404)
        await repo.update(department, next_department_id=next_department_id)
        await session.commit()

    return web.json_response({"id": department_id, "next_department_id": next_department_id})


@routes.post("/departments/{department_id}/autoreassign")
async def toggle_autoreassign(request: web.Request) -> web.Response:
    """8.3-band: bo'lim darajasida 48-soatlik avto-o'tkazish signalini
    yoqish/o'chirish (`/autoreassign` bilan bir xil)."""
    department_id = int(request.match_info["department_id"])
    async with async_session() as session:
        repo = DepartmentRepository(session)
        department = await repo.get_by_id(department_id)
        if department is None:
            return err("not_found", 404)
        new_value = not department.auto_reassign_after_48h
        await repo.update(department, auto_reassign_after_48h=new_value)
        await session.commit()

    return web.json_response({"id": department_id, "auto_reassign_after_48h": new_value})


@routes.get("/brigades")
async def list_brigades(request: web.Request) -> web.Response:
    department_id = request.query.get("department_id")
    async with async_session() as session:
        repo = BrigadeRepository(session)
        brigades = (
            await repo.list_by_department(int(department_id)) if department_id else await repo.list_all()
        )
    return web.json_response([{"id": b.id, "name": b.name} for b in brigades])


@routes.get("/departments/{department_id}/brigadiers")
async def list_department_brigadiers(request: web.Request) -> web.Response:
    """Yangi vazifa/bosqich uchun: rahbar bo'limni tanlagach, faqat SHU
    bo'limdagi brigadalarning brigadirlari (ism-familiyasi bilan) ko'rsatiladi
    — endi vazifa to'g'ridan-to'g'ri xodimga emas, brigadirga beriladi,
    brigadir esa Mini App'da o'z brigadasidagi xodimga topshiradi."""
    department_id = int(request.match_info["department_id"])
    async with async_session() as session:
        brigades = await BrigadeRepository(session).list_by_department(department_id)
        employee_repo = EmployeeRepository(session)
        items = []
        for brigade in brigades:
            if brigade.brigadier_id is None:
                continue
            brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
            if brigadier is None or not brigadier.is_active:
                continue
            items.append(
                {
                    "brigade_id": brigade.id,
                    "brigade_name": brigade.name,
                    "brigadier_id": brigadier.id,
                    "brigadier_name": brigadier.full_name,
                }
            )
    return web.json_response(items)


@routes.post("/tasks")
async def create_task(request: web.Request) -> web.Response:
    body = await request.json()
    title = (body.get("title") or "").strip()
    department_id = body.get("department_id")
    brigadier_id = body.get("brigadier_id")
    if not title or not department_id or not brigadier_id:
        return err("title, department_id, brigadier_id majburiy")

    try:
        deadline = datetime.fromisoformat(body["deadline"])
    except (KeyError, ValueError):
        return err("deadline noto'g'ri formatda (ISO 8601 kerak)")
    if deadline <= datetime.now(deadline.tzinfo):
        return err("deadline kelajakda bo'lishi kerak")

    async with async_session() as session:
        brigades = await BrigadeRepository(session).list_by_department(int(department_id))
        active_brigadier_ids = await _active_brigadier_ids(session, brigades)
    if int(brigadier_id) not in active_brigadier_ids:
        return err("brigadir bu bo'limga tegishli emas")

    client_id = None
    client_phone = (body.get("client_phone") or "").strip()
    client_full_name = (body.get("client_full_name") or "").strip()
    if client_phone and client_full_name:
        client = await client_service.find_or_create_client(
            phone_number=client_phone, full_name=client_full_name
        )
        client_id = client.id

    try:
        task = await task_service.create_task(
            title=title,
            description=body.get("description"),
            deadline=deadline,
            department_id=int(department_id),
            employee_ids=[int(brigadier_id)],
            client_id=client_id,
        )
    except task_service.DepartmentNotFoundError:
        return err("bo'lim topilmadi", 404)
    except task_service.DepartmentNotConfiguredError as exc:
        return err(str(exc), 409)

    return web.json_response({"id": task.id, "status": task.status.value}, status=201)


@routes.get("/employees")
async def list_employees(request: web.Request) -> web.Response:
    department_id = request.query.get("department_id")
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        department_repo = DepartmentRepository(session)

        employees = (
            await employee_repo.list_by_department(int(department_id))
            if department_id
            else await employee_repo.list_all()
        )
        departments = {d.id: d.name for d in await department_repo.list_all()}

    return web.json_response(
        [
            {
                "id": e.id,
                "full_name": e.full_name,
                "role": e.role.value,
                "role_label": ROLE_LABELS.get(e.role, e.role.value),
                "department_id": e.department_id,
                "department": departments.get(e.department_id),
                "is_active": e.is_active,
            }
            for e in sorted(employees, key=lambda e: e.full_name)
        ]
    )


@routes.get("/employees/{employee_id}")
async def employee_detail(request: web.Request) -> web.Response:
    employee_id = int(request.match_info["employee_id"])
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_id(employee_id)
        if employee is None:
            return err("not_found", 404)
        department = (
            await DepartmentRepository(session).get_by_id(employee.department_id)
            if employee.department_id
            else None
        )
        brigade = (
            await BrigadeRepository(session).get_by_id(employee.brigade_id) if employee.brigade_id else None
        )

    return web.json_response(
        {
            "id": employee.id,
            "full_name": employee.full_name,
            "phone_number": employee.phone_number,
            "trello_username": employee.trello_username,
            "role": employee.role.value,
            "role_label": ROLE_LABELS.get(employee.role, employee.role.value),
            "department_id": employee.department_id,
            "department": department.name if department else None,
            "brigade_id": employee.brigade_id,
            "brigade": brigade.name if brigade else None,
            "is_active": employee.is_active,
            "telegram_linked": employee.telegram_id is not None,
        }
    )


@routes.post("/employees/{employee_id}")
async def update_employee(request: web.Request) -> web.Response:
    """5.1-band: Xodim tafsiloti ekranidan tahrirlash — chatning
    `EMPLOYEE_FIELD_LABELS` maydonlari bilan bir xil to'plam, bitta so'rovda
    bir nechta maydon birga yuborilishi mumkin (forma sifatida)."""
    employee_id = int(request.match_info["employee_id"])
    body = await request.json()
    fields: dict[str, object] = {}

    if "full_name" in body:
        full_name = (body["full_name"] or "").strip()
        if not full_name:
            return err("full_name bo'sh bo'lishi mumkin emas")
        fields["full_name"] = full_name
    if "phone_number" in body:
        phone_number = (body["phone_number"] or "").strip()
        if not phone_number:
            return err("phone_number bo'sh bo'lishi mumkin emas")
        fields["phone_number"] = phone_number
    if "role" in body:
        if body["role"] not in {r.value for r in Role}:
            return err("role noto'g'ri")
        fields["role"] = Role(body["role"])
    if "trello_username" in body:
        trello_username = (body["trello_username"] or "").strip() or None
        if trello_username:
            try:
                async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
                    fields["trello_member_id"] = await trello.get_member_id(trello_username)
            except TrelloAPIError:
                return err("trello_username topilmadi", 404)
            fields["trello_username"] = trello_username
        else:
            fields["trello_username"] = None
            fields["trello_member_id"] = None
    if "department_id" in body:
        fields["department_id"] = body["department_id"]
    if "brigade_id" in body:
        fields["brigade_id"] = body["brigade_id"]
    elif "department_id" in body:
        # bo'lim o'zgarganda eski brigada mos kelmasligi mumkin (chat bilan bir xil qoida)
        fields["brigade_id"] = None

    if not fields:
        return err("hech qanday maydon berilmadi")

    try:
        employee = await employee_service.update_employee(employee_id, **fields)
    except employee_service.EmployeeNotFoundError:
        return err("not_found", 404)
    except employee_service.DuplicateNameError as exc:
        return err(str(exc), 409)
    except employee_service.DuplicatePhoneError as exc:
        return err(str(exc), 409)

    return web.json_response({"id": employee.id})


@routes.post("/employees/{employee_id}/toggle-active")
async def toggle_employee_active(request: web.Request) -> web.Response:
    employee_id = int(request.match_info["employee_id"])
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        return err("not_found", 404)

    if employee.is_active:
        await employee_service.deactivate_employee(employee_id)
    else:
        await employee_service.reactivate_employee(employee_id)

    return web.json_response({"id": employee_id, "is_active": not employee.is_active})


@routes.post("/employees")
async def create_employee(request: web.Request) -> web.Response:
    body = await request.json()
    full_name = (body.get("full_name") or "").strip()
    phone_number = (body.get("phone_number") or "").strip()
    role_value = body.get("role")
    if not full_name or not phone_number or role_value not in {r.value for r in Role}:
        return err("full_name, phone_number, role majburiy")

    trello_username = (body.get("trello_username") or "").strip() or None
    trello_member_id = None
    if trello_username:
        try:
            async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
                trello_member_id = await trello.get_member_id(trello_username)
        except TrelloAPIError:
            return err("trello_username topilmadi", 404)

    try:
        employee = await employee_service.create_employee(
            full_name=full_name,
            phone_number=phone_number,
            role=Role(role_value),
            department_id=body.get("department_id"),
            brigade_id=body.get("brigade_id"),
            trello_username=trello_username,
            trello_member_id=trello_member_id,
        )
    except employee_service.DuplicateNameError as exc:
        return err(str(exc), 409)
    except employee_service.DuplicatePhoneError as exc:
        return err(str(exc), 409)

    return web.json_response({"id": employee.id}, status=201)


@routes.get("/financial")
async def list_financial(request: web.Request) -> web.Response:
    async with async_session() as session:
        suggestions = await FinancialSuggestionRepository(session).list_pending()
        task_repo = TaskRepository(session)
        items = []
        for s in suggestions:
            task = await task_repo.get_by_id(s.task_id)
            items.append(
                {
                    "id": s.id,
                    "task_id": s.task_id,
                    "task_title": task.title if task else None,
                    "kind": s.kind.value,
                    "stage_duration_days": s.stage_duration_days,
                    "suggested_deduction_amount": s.suggested_deduction_amount,
                    "waived_amount": s.waived_amount,
                }
            )
    return web.json_response(items)


@routes.post("/financial/{suggestion_id}/amount")
async def set_financial_amount(request: web.Request) -> web.Response:
    suggestion_id = int(request.match_info["suggestion_id"])
    body = await request.json()
    try:
        amount = float(body["amount"])
    except (KeyError, TypeError, ValueError):
        return err("amount noto'g'ri")
    if amount < 0:
        return err("amount manfiy bo'lishi mumkin emas")

    try:
        suggestion = await financial_service.set_wage_deduction_amount(suggestion_id, amount)
    except ValueError as exc:
        return err(str(exc), 404)

    return web.json_response(
        {"id": suggestion.id, "suggested_deduction_amount": suggestion.suggested_deduction_amount}
    )


@routes.post("/financial/advance-waiver")
async def create_advance_waiver(request: web.Request) -> web.Response:
    """8.6-band 2-qoida: `/avanskechirim` bilan bir xil — bitta formada
    task_id/avans%/buyurtma summasi/kechikkanmi."""
    body = await request.json()
    try:
        task_id = int(body["task_id"])
        advance_percent_paid = int(body["advance_percent_paid"])
        order_total_value = float(body["order_total_value"])
        is_late = bool(body["is_late"])
    except (KeyError, TypeError, ValueError):
        return err("task_id, advance_percent_paid, order_total_value, is_late majburiy")
    if not (0 <= advance_percent_paid <= 100):
        return err("advance_percent_paid 0 dan 100 gacha bo'lishi kerak")

    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
    if task is None:
        return err("task topilmadi", 404)

    suggestion = await financial_service.create_advance_waiver_suggestion(
        task_id,
        advance_percent_paid=advance_percent_paid,
        is_late=is_late,
        order_total_value=order_total_value,
    )
    return web.json_response(
        {"id": suggestion.id, "applicable": suggestion.applicable, "waived_amount": suggestion.waived_amount},
        status=201,
    )


@routes.post("/misctasks")
async def create_misc_task(request: web.Request) -> web.Response:
    """9-band: "Vazifalar" moduli — Trello'siz, `/addtask` bilan bir xil."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    employee_ids = body.get("employee_ids") or []
    if not text or not employee_ids:
        return err("text, employee_ids majburiy")
    try:
        deadline = datetime.fromisoformat(body["deadline"])
    except (KeyError, ValueError):
        return err("deadline noto'g'ri formatda (ISO 8601 kerak)")
    if deadline <= datetime.now(deadline.tzinfo):
        return err("deadline kelajakda bo'lishi kerak")

    try:
        task = await task_service.create_misc_task(
            text=text, deadline=deadline, employee_ids=[int(e) for e in employee_ids]
        )
    except ValueError as exc:
        return err(str(exc), 409)

    try:
        await notification_service.notify_task_started(request.config_dict["bot"], task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)

    return web.json_response({"id": task.id, "title": task.title}, status=201)


@routes.get("/stats")
async def full_stats(request: web.Request) -> web.Response:
    """10-band: `/stats`ning to'liq versiyasi — dashboard'dagi xulosa
    tile'laridan farqli, har bir xodim bo'yicha to'liq saralangan jadval.
    Faqat KPI oladigan rollar (ishchi/brigadir) — rahbar/nazoratchi/sotuvchida
    ball umuman bo'lmagani uchun ro'yxatga qo'shilmaydi."""
    stats = sorted(
        (s for s in await stats_service.get_monthly_stats() if s.role in stats_service.KPI_ROLES),
        key=lambda s: s.total_score,
        reverse=True,
    )
    return web.json_response(
        [
            {
                "employee_id": s.employee_id,
                "full_name": s.full_name,
                "role": s.role.value,
                "completed_tasks": s.completed_tasks,
                "total_score": s.total_score,
                "penalty_count": s.penalty_count,
            }
            for s in stats
        ]
    )


_SETTING_FIELDS = list(settings_service.AppSettingsSnapshot.__dataclass_fields__)
_SETTING_FIELDS = [f for f in _SETTING_FIELDS if f not in ("reminder_schedule", "sales_board_lists")]


def _parse_setting_value(field: str, value: object) -> object:
    """`/settings`dagi `_parse_value` bilan bir xil validatsiya qoidalari,
    faqat matn o'rniga JSON qiymatlarni qabul qiladi."""
    if field == "default_penalty_multiplier":
        value = float(value)
        if not (0 < value <= 10):
            raise ValueError
    elif field == "brigade_share_ratio":
        value = float(value)
        if not (0 <= value <= 1):
            raise ValueError
    elif field == "balls_per_day_shift":
        value = int(value)
        if value <= 0:
            raise ValueError
    elif field in (
        "plus_ball_per_day", "plus_ball_max_days", "financial_flag_threshold_days",
        "lead_follow_up_threshold_days",
    ):
        value = int(value)
        if value <= 0:
            raise ValueError
    elif field in ("advance_threshold_percent", "advance_waiver_percent"):
        value = int(value)
        if not (0 <= value <= 100):
            raise ValueError
    elif field == "report_time":
        settings_service.validate_time_str(value)
    else:
        raise ValueError(f"noma'lum sozlama: {field}")
    return value


@routes.get("/settings")
async def get_settings(request: web.Request) -> web.Response:
    snapshot = await settings_service.get_settings()
    return web.json_response({field: getattr(snapshot, field) for field in _SETTING_FIELDS})


@routes.post("/settings")
async def update_settings(request: web.Request) -> web.Response:
    body = await request.json()
    fields: dict[str, object] = {}
    for field in _SETTING_FIELDS:
        if field in body:
            try:
                fields[field] = _parse_setting_value(field, body[field])
            except (TypeError, ValueError):
                return err(f"{field} noto'g'ri qiymat")
    if not fields:
        return err("hech qanday maydon berilmadi")

    updated = await settings_service.update_setting(**fields)
    if "report_time" in fields:
        report_job.schedule_all(request.config_dict["bot"], updated.report_time)

    return web.json_response({field: getattr(updated, field) for field in _SETTING_FIELDS})


@routes.get("/reminders")
async def list_reminders(request: web.Request) -> web.Response:
    snapshot = await settings_service.get_settings()
    return web.json_response(snapshot.reminder_schedule)


@routes.post("/reminders")
async def add_reminder(request: web.Request) -> web.Response:
    body = await request.json()
    snapshot = await settings_service.get_settings()
    schedule = list(snapshot.reminder_schedule)
    schedule.append({"time": (body.get("time") or "").strip(), "urgency": body.get("urgency")})
    try:
        updated = await settings_service.update_setting(reminder_schedule=schedule)
    except settings_service.InvalidReminderScheduleError as exc:
        return err(str(exc))
    reminder_job.schedule_all(request.config_dict["bot"], updated.reminder_schedule)
    return web.json_response(updated.reminder_schedule, status=201)


@routes.put("/reminders/{index}")
async def edit_reminder(request: web.Request) -> web.Response:
    index = int(request.match_info["index"])
    body = await request.json()
    snapshot = await settings_service.get_settings()
    schedule = list(snapshot.reminder_schedule)
    if not 0 <= index < len(schedule):
        return err("not_found", 404)
    schedule[index] = {"time": (body.get("time") or "").strip(), "urgency": body.get("urgency")}
    try:
        updated = await settings_service.update_setting(reminder_schedule=schedule)
    except settings_service.InvalidReminderScheduleError as exc:
        return err(str(exc))
    reminder_job.schedule_all(request.config_dict["bot"], updated.reminder_schedule)
    return web.json_response(updated.reminder_schedule)


@routes.delete("/reminders/{index}")
async def delete_reminder(request: web.Request) -> web.Response:
    index = int(request.match_info["index"])
    snapshot = await settings_service.get_settings()
    schedule = list(snapshot.reminder_schedule)
    if not 0 <= index < len(schedule):
        return err("not_found", 404)
    del schedule[index]
    updated = await settings_service.update_setting(reminder_schedule=schedule)
    reminder_job.schedule_all(request.config_dict["bot"], updated.reminder_schedule)
    return web.json_response(updated.reminder_schedule)


@routes.get("/pending-setup")
async def list_pending_setup(request: web.Request) -> web.Response:
    """6.1/7.4-band: "Sozlash" bildirishnomasi endi Mini App ichidagi shu
    ro'yxat orqali ham ko'rinadi (push xabar hali ham boradi, lekin tugmasiz —
    `notification_service.notify_stage_pending_setup` matnigi qarang)."""
    async with async_session() as session:
        tasks = await TaskRepository(session).list_by_status(TaskStatus.PENDING_SETUP)
        department_repo = DepartmentRepository(session)
        items = []
        for task in tasks:
            department = (
                await department_repo.get_by_id(task.current_department_id)
                if task.current_department_id
                else None
            )
            items.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "department": department.name if department else None,
                    "department_id": task.current_department_id,
                }
            )
    return web.json_response(items)


@routes.post("/tasks/{task_id}/activate")
async def activate_pending_stage(request: web.Request) -> web.Response:
    """6.1/7.4-band: bosqich boshlanganda ham (yangi vazifa yaratishdagi kabi)
    to'g'ridan-to'g'ri xodim emas, SHU bo'limning brigadiri tanlanadi —
    brigadir keyin Mini App'da o'z brigadasidagi xodimga topshiradi."""
    task_id = int(request.match_info["task_id"])
    body = await request.json()
    brigadier_id = body.get("brigadier_id")
    if not brigadier_id:
        return err("brigadier_id majburiy")
    try:
        deadline = datetime.fromisoformat(body["deadline"])
    except (KeyError, ValueError):
        return err("deadline noto'g'ri formatda (ISO 8601 kerak)")
    if deadline <= datetime.now(deadline.tzinfo):
        return err("deadline kelajakda bo'lishi kerak")

    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None or task.current_department_id is None:
            return err("not_found", 404)
        brigades = await BrigadeRepository(session).list_by_department(task.current_department_id)
        active_brigadier_ids = await _active_brigadier_ids(session, brigades)
    if int(brigadier_id) not in active_brigadier_ids:
        return err("brigadir bu bo'limga tegishli emas")

    try:
        task = await task_service.activate_pending_stage(
            task_id, deadline=deadline, employee_ids=[int(brigadier_id)]
        )
    except task_service.TaskNotFoundError:
        return err("not_found", 404)
    except (task_service.InvalidTaskStateError, ValueError) as exc:
        return err(str(exc), 409)

    try:
        await notification_service.notify_task_started(request.config_dict["bot"], task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)

    return web.json_response({"id": task.id, "status": task.status.value})


@routes.get("/reassign-candidates")
async def list_reassign_candidates(request: web.Request) -> web.Response:
    """8.3-band: "Ko'rib chiqish" bildirishnomasi endi Mini App ichidagi shu
    ro'yxat orqali ham ko'rinadi."""
    async with async_session() as session:
        tasks = await TaskRepository(session).list_awaiting_reassignment_review()
        department_repo = DepartmentRepository(session)
        items = []
        for task in tasks:
            department = (
                await department_repo.get_by_id(task.current_department_id)
                if task.current_department_id
                else None
            )
            items.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "department": department.name if department else None,
                    "department_id": task.current_department_id,
                    "deadline": task.deadline.isoformat() if task.deadline else None,
                }
            )
    return web.json_response(items)


@routes.get("/tasks/{task_id}/reassign-brigades")
async def reassign_brigade_options(request: web.Request) -> web.Response:
    task_id = int(request.match_info["task_id"])
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None or task.current_department_id is None:
            return err("not_found", 404)

        current_brigade_id = None
        for assignment in await TaskAssignmentRepository(session).list_by_task(task_id):
            employee = await EmployeeRepository(session).get_by_id(assignment.employee_id)
            if employee is not None and employee.brigade_id is not None:
                current_brigade_id = employee.brigade_id
                break

        brigades = await BrigadeRepository(session).list_by_department(task.current_department_id)
    return web.json_response([{"id": b.id, "name": b.name} for b in brigades if b.id != current_brigade_id])


@routes.post("/tasks/{task_id}/reassign")
async def reassign_task(request: web.Request) -> web.Response:
    task_id = int(request.match_info["task_id"])
    body = await request.json()
    try:
        new_brigade_id = int(body["brigade_id"])
    except (KeyError, TypeError, ValueError):
        return err("brigade_id majburiy")

    async with async_session() as session:
        old_employee_ids = [
            a.employee_id for a in await TaskAssignmentRepository(session).list_by_task(task_id)
        ]

    try:
        await task_service.reassign_task_brigade(task_id, new_brigade_id)
    except task_service.TaskNotFoundError:
        return err("not_found", 404)
    except (task_service.InvalidTaskStateError, ValueError) as exc:
        return err(str(exc), 409)

    async with async_session() as session:
        new_employee_ids = [e.id for e in await EmployeeRepository(session).list_by_brigade(new_brigade_id)]

    try:
        await notification_service.notify_task_reassigned(
            request.config_dict["bot"], task_id, old_employee_ids=old_employee_ids, new_employee_ids=new_employee_ids
        )
    except Exception:
        logger.exception("notify_task_reassigned xatosi (task_id=%s)", task_id)

    return web.json_response({"id": task_id, "status": "reassigned"})
