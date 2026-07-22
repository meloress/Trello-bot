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
    TaskRepository,
)
from config import settings
from keyboards.admin_kb import ROLE_LABELS
from miniapp.util import err
from services import client_service, employee_service, financial_service, stats_service, task_service
from trello.client import TrelloAPIError, TrelloClient
from utils.enums import Role

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


@routes.get("/dashboard")
async def dashboard(request: web.Request) -> web.Response:
    stats = await stats_service.get_monthly_stats()
    active_employees = len(stats)
    completed_total = sum(s.completed_tasks for s in stats)
    avg_score = round(sum(s.total_score for s in stats) / active_employees) if active_employees else 0
    top = max(stats, key=lambda s: s.total_score, default=None)

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
    return web.json_response([{"id": d.id, "name": d.name} for d in departments])


@routes.get("/brigades")
async def list_brigades(request: web.Request) -> web.Response:
    department_id = request.query.get("department_id")
    async with async_session() as session:
        repo = BrigadeRepository(session)
        brigades = (
            await repo.list_by_department(int(department_id)) if department_id else await repo.list_all()
        )
    return web.json_response([{"id": b.id, "name": b.name} for b in brigades])


@routes.post("/tasks")
async def create_task(request: web.Request) -> web.Response:
    body = await request.json()
    title = (body.get("title") or "").strip()
    department_id = body.get("department_id")
    employee_ids = body.get("employee_ids") or []
    if not title or not department_id or not employee_ids:
        return err("title, department_id, employee_ids majburiy")

    try:
        deadline = datetime.fromisoformat(body["deadline"])
    except (KeyError, ValueError):
        return err("deadline noto'g'ri formatda (ISO 8601 kerak)")

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
            employee_ids=[int(e) for e in employee_ids],
            client_id=client_id,
        )
    except task_service.DepartmentNotFoundError:
        return err("bo'lim topilmadi", 404)
    except task_service.DepartmentNotConfiguredError as exc:
        return err(str(exc), 409)

    return web.json_response({"id": task.id, "status": task.status.value}, status=201)


@routes.get("/employees")
async def list_employees(request: web.Request) -> web.Response:
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        department_repo = DepartmentRepository(session)

        employees = await employee_repo.list_all()
        departments = {d.id: d.name for d in await department_repo.list_all()}

    return web.json_response(
        [
            {
                "id": e.id,
                "full_name": e.full_name,
                "role": e.role.value,
                "role_label": ROLE_LABELS.get(e.role, e.role.value),
                "department": departments.get(e.department_id),
                "is_active": e.is_active,
            }
            for e in sorted(employees, key=lambda e: e.full_name)
        ]
    )


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

    try:
        suggestion = await financial_service.set_wage_deduction_amount(suggestion_id, amount)
    except ValueError as exc:
        return err(str(exc), 404)

    return web.json_response(
        {"id": suggestion.id, "suggested_deduction_amount": suggestion.suggested_deduction_amount}
    )
