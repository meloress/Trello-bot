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
from miniapp.util import err, is_label_order, is_mebel_task, is_trello_owned_order
from services import claim_service, employee_service, notification_service, penalty_service, stats_service, task_service
from utils.enums import ClaimActionType, Role, TaskStatus, TaskType

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


async def _own_brigades(session, employee) -> list:
    """So'rovchining ko'rish doirasidagi brigadalar: BRIGADIER uchun o'zi
    boshqargan BARCHA brigadalar (bitta odam Kraska va Shkurkaga birga
    rahbarlik qilishi mumkin), SUPERVISOR uchun o'z bo'limidagilar
    (bo'limsiz SUPERVISOR — barchasi)."""
    brigade_repo = BrigadeRepository(session)
    if employee.role == Role.BRIGADIER:
        return await brigade_repo.list_by_brigadier_id(employee.id)
    if employee.department_id is not None:
        return await brigade_repo.list_by_department(employee.department_id)
    return await brigade_repo.list_all()


async def _resolve_brigade(request: web.Request):
    """`brigade_id` so'rov parametri DOIM so'rovchining o'z doirasidan
    tanlanadi — begona bo'lim/brigada id'sini berib ko'rib bo'lmaydi.
    Parametrsiz — birinchisi (bitta brigadasi bor odam uchun o'zgarishsiz)."""
    async with async_session() as session:
        brigades = await _own_brigades(session, request["employee"])

    brigade_id = request.query.get("brigade_id")
    if brigade_id:
        return next((b for b in brigades if b.id == int(brigade_id)), None)
    return brigades[0] if brigades else None


async def _employee_in_scope(request: web.Request, employee_id: int) -> bool:
    """`/members/{employee_id}/...` — so'ralgan xodim so'rovchining ko'rish
    doirasiga tegishli ekanini tekshiradi: BRIGADIER uchun o'zi boshqargan
    brigadalarning BIRORTASI, SUPERVISOR uchun o'z bo'limi (bo'limi yo'q
    SUPERVISOR — barcha xodimlar, `_resolve_brigade`dagi bilan bir xil qoida)."""
    employee = request["employee"]
    async with async_session() as session:
        target = await EmployeeRepository(session).get_by_id(employee_id)
        if target is None:
            return False
        if employee.role == Role.BRIGADIER:
            brigade_ids = {b.id for b in await BrigadeRepository(session).list_by_brigadier_id(employee.id)}
            return target.brigade_id in brigade_ids
        if employee.department_id is not None:
            return target.department_id == employee.department_id
        return True


@routes.get("/brigades")
async def list_brigades(request: web.Request) -> web.Response:
    """Brigada tanlash ro'yxati — BRIGADIER uchun o'zi boshqargan brigadalar
    (ilgari bu yerda ham bo'lim bo'yicha qidirilardi, ya'ni brigadirga o'z
    bo'limidagi BEGONA brigadalar ham ko'rinardi)."""
    async with async_session() as session:
        brigades = await _own_brigades(session, request["employee"])
    return web.json_response([{"id": b.id, "name": b.name} for b in brigades])


@routes.get("/brigade")
async def brigade_overview(request: web.Request) -> web.Response:
    brigade = await _resolve_brigade(request)
    if brigade is None:
        return err("brigada topilmadi", 404)

    employee = request["employee"]
    async with async_session() as session:
        brigades = await _own_brigades(session, employee)

    # Brigadirning o'z bali brigadadan MUSTAQIL hisoblanadi: ikkita brigadaga
    # rahbarlik qilsa, `employees.brigade_id` faqat bittasiga ishora qiladi va
    # ikkinchi brigada ekranida o'z bali "—" bo'lib qolardi.
    since, until = penalty_service.month_bounds(datetime.now(timezone.utc).date())
    own_score = await penalty_service.calculate_total_score(employee.id, since=since, until=until)

    stats = await stats_service.get_brigade_monthly_stats(brigade.id)
    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(brigade.department_id)
    return web.json_response(
        {
            "id": brigade.id,
            "name": brigade.name,
            "can_add_members": employee.role == Role.BRIGADIER and bool(department and department.trello_label),
            "own_score": own_score,
            "brigades": [{"id": b.id, "name": b.name} for b in brigades],
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
            department = None
            if task.current_department_id is not None:
                department = await department_repo.get_by_id(task.current_department_id)
            items.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "deadline": task.deadline.isoformat() if task.deadline else None,
                    "module": department.module if department else None,
                    # raspil (label) zakazi — ishchini shu yerda belgilaydi, qolgani Trello'da
                    "delegable": bool(department and department.trello_label),
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


@routes.post("/members")
async def add_member(request: web.Request) -> web.Response:
    """Raspil brigadiri o'z brigadasiga yangi ishchi qo'shadi (ism + telefon), u keyin
    botga /start bosib kiradi (2026-11-14, user). Faqat label bo'limlari: boshqa
    bo'limlarda xodimni admin qo'shadi."""
    employee = request["employee"]
    if employee.role != Role.BRIGADIER:
        return err("faqat brigadir", 403)
    brigade = await _resolve_brigade(request)
    if brigade is None:
        return err("brigada topilmadi", 404)
    body = await request.json()
    full_name = (body.get("full_name") or "").strip()
    phone_number = (body.get("phone_number") or "").strip()
    if not full_name or sum(c.isdigit() for c in phone_number) < 9:
        return err("Ism va telefon raqam (kamida 9 raqam) majburiy")
    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(brigade.department_id)
        if department is None or not department.trello_label:
            return err("Bu bo'limga xodimni admin qo'shadi", 403)
        # admin turli formatda yozgan bo'lishi mumkin — ro'yxatdan o'tish shu solishtirish bilan
        if await EmployeeRepository(session).find_by_normalized_phone(phone_number):
            return err("Bu raqamli xodim allaqachon bor", 409)
    try:
        worker = await employee_service.create_employee(
            full_name=full_name, phone_number=phone_number, role=Role.WORKER,
            department_id=brigade.department_id, brigade_id=brigade.id,
        )
    except (employee_service.DuplicateNameError, employee_service.DuplicatePhoneError) as exc:
        return err(str(exc), 409)
    logger.info("brigadir %s brigadaga ishchi qo'shdi: %s", employee.id, worker.id)
    return web.json_response({"id": worker.id}, status=201)


@routes.post("/tasks/{task_id}/delegate")
async def delegate_task(request: web.Request) -> web.Response:
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    body = await request.json()
    worker_ids = [int(e) for e in (body.get("employee_ids") or [])]
    if not worker_ids:
        return err("employee_ids majburiy")

    if await is_mebel_task(task_id) or (await is_trello_owned_order(task_id) and not await is_label_order(task_id)):
        return err(
            "Bu zakaz Trello orqali topshiriladi — ishchini Trello kartaga a'zo qiling.",
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


@routes.post("/members/{employee_id}/tasks/{task_id}/resume-claim")
async def submit_member_resume_claim(request: web.Request) -> web.Response:
    """To'xtatilgan (STOPPED) vazifani davom ettirish — Pauza/Yakunlash bilan
    BIR XIL qoida: brigadir so'rov yuboradi, rahbar/admin tasdiqlaguncha
    vazifa STOPPED holicha qoladi. Ilgari bu darhol ishlar edi."""
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
            task_id, employee_id, ClaimActionType.RESUME, datetime.now(timezone.utc),
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
