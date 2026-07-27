"""Brigadir ekranlari: brigada a'zolari + joriy oy KPI, a'zoning haftalik
hisoboti va joriy vazifalari. Ruxsat: Role.BRIGADIER/Role.SUPERVISOR.

`handlers/brigadier/stats.py` bilan bir xil mantiq: BRIGADIER uchun
boshqaradigan brigada avtomatik topiladi; SUPERVISOR `brigade_id` so'rov
parametri orqali (o'z bo'limidagi yoki barcha) brigadalardan birini tanlaydi.
"""

import logging
from datetime import datetime, timezone

from aiohttp import web
from sqlalchemy.exc import IntegrityError

from core.database import async_session
from db.repositories import (
    BrigadeRepository,
    DepartmentRepository,
    EmployeeRepository,
    TaskAssignmentRepository,
    TaskClaimRepository,
    TaskRepository,
)
from miniapp.util import err, is_mebel_task
from services import claim_service, notification_service, stats_service, task_service, timer_service
from utils.enums import ClaimActionType, Role, TaskStatus, TaskType

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


async def _resolve_brigade(request: web.Request):
    """BRIGADIER uchun faqat o'zi boshqargan brigada. SUPERVISOR uchun
    `brigade_id` so'rov parametri ham berilsa, faqat O'Z BO'LIMIdagi
    brigadalar orasidan tanlanadi — boshqa bo'lim brigadasini `brigade_id`
    orqali ko'rish oldini olish uchun (ilgari cheklovsiz edi)."""
    employee = request["employee"]
    async with async_session() as session:
        brigade_repo = BrigadeRepository(session)
        if employee.role == Role.BRIGADIER:
            return await brigade_repo.get_by_brigadier_id(employee.id)

        if employee.department_id is not None:
            brigades = await brigade_repo.list_by_department(employee.department_id)
        else:
            brigades = await brigade_repo.list_all()

        brigade_id = request.query.get("brigade_id")
        if brigade_id:
            return next((b for b in brigades if b.id == int(brigade_id)), None)
        return brigades[0] if brigades else None


async def _employee_in_scope(request: web.Request, employee_id: int) -> bool:
    """`/members/{employee_id}/...` — so'ralgan xodim so'rovchining ko'rish
    doirasiga tegishli ekanini tekshiradi: BRIGADIER uchun o'z brigadasi,
    SUPERVISOR uchun o'z bo'limi (bo'limi yo'q SUPERVISOR — barcha xodimlar,
    `_resolve_brigade`dagi bilan bir xil qoida)."""
    employee = request["employee"]
    async with async_session() as session:
        target = await EmployeeRepository(session).get_by_id(employee_id)
        if target is None:
            return False
        if employee.role == Role.BRIGADIER:
            brigade = await BrigadeRepository(session).get_by_brigadier_id(employee.id)
            return brigade is not None and target.brigade_id == brigade.id
        if employee.department_id is not None:
            return target.department_id == employee.department_id
        return True


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
    if not await _employee_in_scope(request, employee_id):
        return err("xodim topilmadi", 404)
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
        department_repo = DepartmentRepository(session)

        assignments = await assignment_repo.list_by_employee(employee.id)
        items = []
        for assignment in assignments:
            task = await task_repo.get_by_id(assignment.task_id)
            if task is None or task.task_type != TaskType.ORDER or task.status == TaskStatus.COMPLETED:
                continue
            module = None
            if task.current_department_id is not None:
                department = await department_repo.get_by_id(task.current_department_id)
                module = department.module if department else None
            items.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "deadline": task.deadline.isoformat() if task.deadline else None,
                    "module": module,
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

    if await is_mebel_task(task_id):
        return err(
            "Mebel bo'limida vazifani botdan turib topshirib bo'lmaydi — ishchini Trello kartaga a'zo qiling.",
            409,
        )

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
    if not await _employee_in_scope(request, employee_id):
        return err("xodim topilmadi", 404)
    async with async_session() as session:
        assignment_repo = TaskAssignmentRepository(session)
        task_repo = TaskRepository(session)
        department_repo = DepartmentRepository(session)

        assignments = await assignment_repo.list_by_employee(employee_id)
        items = []
        for assignment in assignments:
            task = await task_repo.get_by_id(assignment.task_id)
            if task is not None and task.status != TaskStatus.COMPLETED:
                module = None
                if task.current_department_id is not None:
                    department = await department_repo.get_by_id(task.current_department_id)
                    module = department.module if department else None
                items.append(
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status.value,
                        "deadline": task.deadline.isoformat() if task.deadline else None,
                        "module": module,
                    }
                )
    return web.json_response(items)


async def _is_member_assigned(task_id: int, employee_id: int) -> bool:
    async with async_session() as session:
        assignments = await TaskAssignmentRepository(session).list_by_task(task_id)
    return any(a.employee_id == employee_id for a in assignments)


@routes.get("/members/{employee_id}/tasks/{task_id}")
async def member_task_detail(request: web.Request) -> web.Response:
    """`miniapp/api/worker.py`'ning `GET /tasks/{id}`siga o'xshash, lekin
    brigadir o'zining bir a'zosi uchun ochadi — mebel'da ishchi profilida
    Pauza/Yakunlash yo'qligi sabab, shu ekran o'sha amallarni ko'rsatadi."""
    employee_id = int(request.match_info["employee_id"])
    task_id = int(request.match_info["task_id"])
    if not await _employee_in_scope(request, employee_id):
        return err("xodim topilmadi", 404)
    if not await _is_member_assigned(task_id, employee_id):
        return err("not_found", 404)

    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            return err("not_found", 404)
        module = None
        department_name = None
        if task.current_department_id is not None:
            department = await DepartmentRepository(session).get_by_id(task.current_department_id)
            module = department.module if department else None
            department_name = department.name if department else None

    return web.json_response(
        {
            "id": task.id,
            "title": task.title,
            "status": task.status.value,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "department": department_name,
            "module": module,
        }
    )


@routes.post("/members/{employee_id}/tasks/{task_id}/pause-claim")
async def submit_member_pause_claim(request: web.Request) -> web.Response:
    """Mebel moduli: ishchi profilida Pauza/Yakunlash tugmasi yo'q — brigadir
    o'z brigadasidagi ishchining vazifasini shu yerdan (ishchi tafsiloti
    ekranidan) turib pauza/yakunlashga so'rov yuboradi. Claim'ning o'zi
    baribir ISHCHI nomidan yoziladi (`employee_id`) — bu brigadirning UI
    orqali qilgan amali, ishning egasi hamon ishchi (`claim_service`dagi
    "kim bosdi" emas, "kimning ishi" tushunchasi)."""
    employee_id = int(request.match_info["employee_id"])
    task_id = int(request.match_info["task_id"])
    if not await _employee_in_scope(request, employee_id):
        return err("xodim topilmadi", 404)
    if not await _is_member_assigned(task_id, employee_id):
        return err("not_found", 404)
    if not await is_mebel_task(task_id):
        return err("Bu funksiya faqat mebel moduli uchun", 409)
    body = await request.json()
    reason = (body.get("reason") or "").strip()

    try:
        claim = await claim_service.submit_claim(
            task_id, employee_id, ClaimActionType.PAUSE, datetime.now(timezone.utc), reason=reason,
        )
    except claim_service.ClaimAlreadyPendingError as exc:
        return err(str(exc), 409)
    except IntegrityError:
        return err("Bu vazifa uchun allaqachon so'rov yuborilgan", 409)
    except ValueError as exc:
        return err(str(exc))

    try:
        await notification_service.notify_claim_submitted(request.config_dict["bot"], claim.id)
    except Exception:
        logger.exception("notify_claim_submitted xatosi (claim_id=%s)", claim.id)

    return web.json_response({"id": claim.id, "status": claim.status.value})


@routes.post("/members/{employee_id}/tasks/{task_id}/finish-claim")
async def submit_member_finish_claim(request: web.Request) -> web.Response:
    employee_id = int(request.match_info["employee_id"])
    task_id = int(request.match_info["task_id"])
    if not await _employee_in_scope(request, employee_id):
        return err("xodim topilmadi", 404)
    if not await _is_member_assigned(task_id, employee_id):
        return err("not_found", 404)
    if not await is_mebel_task(task_id):
        return err("Bu funksiya faqat mebel moduli uchun", 409)

    try:
        claim = await claim_service.submit_claim(
            task_id, employee_id, ClaimActionType.FINISH, datetime.now(timezone.utc),
        )
    except claim_service.ClaimAlreadyPendingError as exc:
        return err(str(exc), 409)
    except IntegrityError:
        return err("Bu vazifa uchun allaqachon so'rov yuborilgan", 409)

    try:
        await notification_service.notify_claim_submitted(request.config_dict["bot"], claim.id)
    except Exception:
        logger.exception("notify_claim_submitted xatosi (claim_id=%s)", claim.id)

    return web.json_response({"id": claim.id, "status": claim.status.value})


@routes.post("/members/{employee_id}/tasks/{task_id}/resume")
async def resume_member_task(request: web.Request) -> web.Response:
    """Mebel moduli: to'xtatilgan (STOPPED) vazifani brigadir a'zosi nomidan
    davom ettiradi. Pauza/Yakunlashdan farqli o'laroq claim-gated EMAS —
    rahbar tasdig'i shart emas, `timer_service.resume_task()` darhol
    ishlaydi; rahbarga faqat xabar ketadi (`notify_task_resumed`)."""
    employee_id = int(request.match_info["employee_id"])
    task_id = int(request.match_info["task_id"])
    if not await _employee_in_scope(request, employee_id):
        return err("xodim topilmadi", 404)
    if not await _is_member_assigned(task_id, employee_id):
        return err("not_found", 404)
    if not await is_mebel_task(task_id):
        return err("Bu funksiya faqat mebel moduli uchun", 409)

    try:
        task = await timer_service.resume_task(task_id, employee_id)
    except timer_service.TaskNotFoundError:
        return err("not_found", 404)
    except timer_service.InvalidTaskStateError as exc:
        return err(str(exc), 409)

    try:
        await notification_service.notify_task_resumed(request.config_dict["bot"], task.id, employee_id)
    except Exception:
        logger.exception("notify_task_resumed xatosi (task_id=%s)", task.id)

    return web.json_response({"id": task.id, "status": task.status.value})


@routes.get("/members/{employee_id}/tasks/{task_id}/claim-status")
async def member_claim_status(request: web.Request) -> web.Response:
    employee_id = int(request.match_info["employee_id"])
    task_id = int(request.match_info["task_id"])
    if not await _employee_in_scope(request, employee_id):
        return err("xodim topilmadi", 404)
    if not await _is_member_assigned(task_id, employee_id):
        return err("not_found", 404)

    async with async_session() as session:
        claim = await TaskClaimRepository(session).get_pending_for_task(task_id)

    if claim is None:
        return web.json_response({"pending_claim": None})
    return web.json_response(
        {"pending_claim": {"id": claim.id, "action_type": claim.action_type.value, "claimed_at": claim.claimed_at.isoformat()}}
    )
