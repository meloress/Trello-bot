"""Brigadir ekranlari: brigada a'zolari + joriy oy KPI, a'zoning haftalik
hisoboti va joriy vazifalari. Ruxsat: Role.BRIGADIER/Role.SUPERVISOR.

`handlers/brigadier/stats.py` bilan bir xil mantiq: BRIGADIER uchun
boshqaradigan brigada avtomatik topiladi; SUPERVISOR `brigade_id` so'rov
parametri orqali (o'z bo'limidagi yoki barcha) brigadalardan birini tanlaydi.
"""

import logging

from aiohttp import web

from core.database import async_session
from db.repositories import BrigadeRepository, EmployeeRepository, TaskAssignmentRepository, TaskRepository
from miniapp.util import err
from services import notification_service, stats_service, task_service
from utils.enums import Role, TaskStatus, TaskType

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


async def _resolve_brigade(request: web.Request):
    employee = request["employee"]
    async with async_session() as session:
        brigade_repo = BrigadeRepository(session)
        if employee.role == Role.BRIGADIER:
            return await brigade_repo.get_by_brigadier_id(employee.id)

        brigade_id = request.query.get("brigade_id")
        if brigade_id:
            return await brigade_repo.get_by_id(int(brigade_id))
        if employee.department_id is not None:
            brigades = await brigade_repo.list_by_department(employee.department_id)
        else:
            brigades = await brigade_repo.list_all()
        return brigades[0] if brigades else None


@routes.get("/brigades")
async def list_brigades(request: web.Request) -> web.Response:
    """SUPERVISOR uchun brigada tanlash ro'yxati (o'z bo'limi doirasida)."""
    employee = request["employee"]
    async with async_session() as session:
        brigade_repo = BrigadeRepository(session)
        if employee.department_id is not None:
            brigades = await brigade_repo.list_by_department(employee.department_id)
        else:
            brigades = await brigade_repo.list_all()
    return web.json_response([{"id": b.id, "name": b.name} for b in brigades])


@routes.get("/brigade")
async def brigade_overview(request: web.Request) -> web.Response:
    brigade = await _resolve_brigade(request)
    if brigade is None:
        return err("brigada topilmadi", 404)

    stats = await stats_service.get_brigade_monthly_stats(brigade.id)
    return web.json_response(
        {
            "id": brigade.id,
            "name": brigade.name,
            "members": [
                {
                    "employee_id": s.employee_id,
                    "full_name": s.full_name,
                    "total_score": s.total_score,
                    "penalty_count": s.penalty_count,
                    "completed_tasks": s.completed_tasks,
                }
                for s in stats
            ],
        }
    )


@routes.get("/members/{employee_id}/report")
async def member_weekly_report(request: web.Request) -> web.Response:
    employee_id = int(request.match_info["employee_id"])
    stats = await stats_service.get_employee_weekly_stats(employee_id)
    if stats is None:
        return err("xodim topilmadi", 404)
    return web.json_response(
        {
            "full_name": stats.full_name,
            "completed_tasks": stats.completed_tasks,
            "total_score": stats.total_score,
            "penalty_count": stats.penalty_count,
        }
    )


@routes.get("/pending-delegation")
async def list_pending_delegation(request: web.Request) -> web.Response:
    """Brigadirga to'g'ridan-to'g'ri tushgan, hali o'z brigadasidagi biror
    xodimga topshirilmagan vazifalar ("Yangi ish" navbati) — `create_task()`/
    `activate_pending_stage()` endi vazifani xuddi shu brigadirga beradi,
    brigadir buni ko'rib, `POST /tasks/{id}/delegate` orqali xodimga topshiradi.
    Topshirilgach brigadir `task_assignments`dan chiqib ketadi, shu sabab bu
    ro'yxat avtomatik bo'shab boradi — alohida "delegated" bayrog'i shart emas."""
    employee = request["employee"]
    async with async_session() as session:
        assignment_repo = TaskAssignmentRepository(session)
        task_repo = TaskRepository(session)

        assignments = await assignment_repo.list_by_employee(employee.id)
        items = []
        for assignment in assignments:
            task = await task_repo.get_by_id(assignment.task_id)
            if task is None or task.task_type != TaskType.ORDER or task.status == TaskStatus.COMPLETED:
                continue
            items.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "deadline": task.deadline.isoformat() if task.deadline else None,
                }
            )
    return web.json_response(items)


@routes.get("/brigade-members")
async def list_brigade_members(request: web.Request) -> web.Response:
    """Brigadir vazifani topshirishi uchun O'Z brigadasidagi faol xodimlar."""
    brigade = await _resolve_brigade(request)
    if brigade is None:
        return err("brigada topilmadi", 404)
    async with async_session() as session:
        members = await EmployeeRepository(session).list_by_brigade(brigade.id)
    return web.json_response([{"id": m.id, "full_name": m.full_name} for m in members])


@routes.post("/tasks/{task_id}/delegate")
async def delegate_task(request: web.Request) -> web.Response:
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    body = await request.json()
    worker_ids = [int(e) for e in (body.get("employee_ids") or [])]
    if not worker_ids:
        return err("employee_ids majburiy")

    brigade = await _resolve_brigade(request)
    if brigade is None:
        return err("brigada topilmadi", 404)
    async with async_session() as session:
        own_member_ids = {m.id for m in await EmployeeRepository(session).list_by_brigade(brigade.id)}
    if not set(worker_ids) <= own_member_ids:
        return err("faqat o'z brigadangizdagi xodimlarga topshirishingiz mumkin", 403)

    try:
        task = await task_service.delegate_task(task_id, brigadier_id=employee.id, worker_ids=worker_ids)
    except task_service.TaskNotFoundError:
        return err("not_found", 404)
    except (task_service.InvalidTaskStateError, ValueError) as exc:
        return err(str(exc), 409)

    try:
        await notification_service.notify_task_started(request.config_dict["bot"], task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)

    return web.json_response({"id": task.id, "status": task.status.value})


@routes.get("/members/{employee_id}/tasks")
async def member_tasks(request: web.Request) -> web.Response:
    employee_id = int(request.match_info["employee_id"])
    async with async_session() as session:
        assignment_repo = TaskAssignmentRepository(session)
        task_repo = TaskRepository(session)

        assignments = await assignment_repo.list_by_employee(employee_id)
        items = []
        for assignment in assignments:
            task = await task_repo.get_by_id(assignment.task_id)
            if task is not None and task.status != TaskStatus.COMPLETED:
                items.append(
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status.value,
                        "deadline": task.deadline.isoformat() if task.deadline else None,
                    }
                )
    return web.json_response(items)
