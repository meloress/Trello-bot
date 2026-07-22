"""Ishchi ekranlari: buyurtmalar/vazifalar ro'yxati, vazifa detali va
Boshlash/Stop/Davom ettirish/Yakunlash amallari, ball tarixi.

Har bir yozuv amali mavjud `timer_service`/`task_service`/`penalty_service`
funksiyalarini chaqiradi — chatdagi `handlers/worker/tasks.py` bilan bir xil
kod yo'lidan o'tadi, mantiq ikki marta yozilmagan.
"""

import logging
from datetime import datetime, timezone

from aiohttp import web

from core.database import async_session
from db.repositories import (
    ClientRepository,
    DepartmentRepository,
    KpiLogRepository,
    TaskAssignmentRepository,
    TaskRepository,
)
from miniapp.util import err
from services import notification_service, penalty_service, task_service, timer_service
from utils.enums import TaskStatus, TaskType

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


async def _list_my_tasks(employee_id: int, task_type: TaskType) -> list[dict]:
    async with async_session() as session:
        assignment_repo = TaskAssignmentRepository(session)
        task_repo = TaskRepository(session)
        department_repo = DepartmentRepository(session)

        assignments = await assignment_repo.list_by_employee(employee_id)
        items: list[dict] = []
        for assignment in assignments:
            task = await task_repo.get_by_id(assignment.task_id)
            if task is None or task.status == TaskStatus.COMPLETED or task.task_type != task_type:
                continue

            department_name = None
            if task.current_department_id is not None:
                department = await department_repo.get_by_id(task.current_department_id)
                department_name = department.name if department else None

            items.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status.value,
                    "deadline": task.deadline.isoformat() if task.deadline else None,
                    "department": department_name,
                }
            )
        return items


@routes.get("/tasks")
async def list_tasks(request: web.Request) -> web.Response:
    employee = request["employee"]
    return web.json_response(await _list_my_tasks(employee.id, TaskType.ORDER))


@routes.get("/misctasks")
async def list_misctasks(request: web.Request) -> web.Response:
    employee = request["employee"]
    return web.json_response(await _list_my_tasks(employee.id, TaskType.MISC))


@routes.get("/tasks/{task_id}")
async def task_detail(request: web.Request) -> web.Response:
    task_id = int(request.match_info["task_id"])
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            return err("not_found", 404)

        department_name = None
        if task.current_department_id is not None:
            department = await DepartmentRepository(session).get_by_id(task.current_department_id)
            department_name = department.name if department else None

        client_name = None
        if task.client_id is not None:
            client = await ClientRepository(session).get_by_id(task.client_id)
            client_name = client.full_name if client else None

    return web.json_response(
        {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "department": department_name,
            "client_name": client_name,
        }
    )


@routes.post("/tasks/{task_id}/start")
async def start_task(request: web.Request) -> web.Response:
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    try:
        task = await timer_service.start_task(task_id, [employee.id])
    except timer_service.TaskNotFoundError:
        return err("not_found", 404)
    except timer_service.InvalidTaskStateError as exc:
        return err(str(exc), 409)

    try:
        await notification_service.notify_task_started(request.config_dict["bot"], task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)

    return web.json_response({"id": task.id, "status": task.status.value})


@routes.post("/tasks/{task_id}/stop")
async def stop_task(request: web.Request) -> web.Response:
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    body = await request.json()
    reason = (body.get("reason") or "").strip()

    try:
        stop_log = await timer_service.stop_task(task_id, employee.id, reason)
    except timer_service.TaskNotFoundError:
        return err("not_found", 404)
    except (timer_service.InvalidTaskStateError, ValueError) as exc:
        return err(str(exc), 409)

    bot = request.config_dict["bot"]
    try:
        await notification_service.notify_task_stopped(bot, stop_log.id)
    except Exception:
        logger.exception("notify_task_stopped xatosi (stop_log_id=%s)", stop_log.id)
    try:
        await notification_service.notify_client_task_stopped(bot, stop_log.id)
    except Exception:
        logger.exception("notify_client_task_stopped xatosi (stop_log_id=%s)", stop_log.id)

    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
    return web.json_response({"id": task.id, "status": task.status.value})


@routes.post("/tasks/{task_id}/resume")
async def resume_task(request: web.Request) -> web.Response:
    task_id = int(request.match_info["task_id"])
    try:
        task = await timer_service.resume_task(task_id)
    except timer_service.TaskNotFoundError:
        return err("not_found", 404)
    except timer_service.InvalidTaskStateError as exc:
        return err(str(exc), 409)

    return web.json_response({"id": task.id, "status": task.status.value})


@routes.post("/tasks/{task_id}/finish")
async def finish_task(request: web.Request) -> web.Response:
    task_id = int(request.match_info["task_id"])
    try:
        task = await timer_service.finish_task(task_id)
    except timer_service.TaskNotFoundError:
        return err("not_found", 404)
    except timer_service.InvalidTaskStateError as exc:
        return err(str(exc), 409)

    bot = request.config_dict["bot"]

    # 8.1/8.2/8.4-band: kechikish/erta tugatish jarima-ball hisob-kitobi —
    # chatdagi on_finish_task bilan bir xil, qoida sozlanmagan bo'lsa ham
    # "Yakunlash" amali muvaffaqiyatli qoladi (faqat log qilinadi).
    try:
        kpi_logs = await penalty_service.calculate_and_apply_task_penalty(task.id)
    except penalty_service.PenaltyRuleNotConfiguredError:
        logger.warning("Task %s uchun kechikish qoidasi topilmadi", task.id)
        kpi_logs = []
    except Exception:
        logger.exception("calculate_and_apply_task_penalty xatosi (task_id=%s)", task.id)
        kpi_logs = []

    for kpi_log in kpi_logs:
        try:
            await notification_service.notify_penalty_applied(bot, kpi_log.id)
        except Exception:
            logger.exception("notify_penalty_applied xatosi (kpi_log_id=%s)", kpi_log.id)

    if task.task_type == TaskType.ORDER:
        try:
            next_task = await task_service.advance_task_stage(task.id)
        except Exception:
            logger.exception("advance_task_stage xatosi (task_id=%s)", task.id)
            next_task = None

        try:
            await notification_service.notify_client_stage_advanced(bot, task.id)
        except Exception:
            logger.exception("notify_client_stage_advanced xatosi (task_id=%s)", task.id)

        if next_task is not None:
            try:
                await notification_service.notify_stage_pending_setup(bot, next_task.id)
            except Exception:
                logger.exception("notify_stage_pending_setup xatosi (task_id=%s)", next_task.id)

    return web.json_response({"id": task.id, "status": task.status.value})


@routes.get("/score")
async def score(request: web.Request) -> web.Response:
    employee = request["employee"]
    since, until = penalty_service.month_bounds(datetime.now(timezone.utc).date())
    total = await penalty_service.calculate_total_score(employee.id, since=since, until=until)

    async with async_session() as session:
        logs = await KpiLogRepository(session).list_by_employee_in_range(employee.id, since, until)

    return web.json_response(
        {
            "total": total,
            "logs": [
                {
                    "score": log.score,
                    "reason": log.reason,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ],
        }
    )
