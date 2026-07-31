"""Ishchi ekranlari: buyurtmalar/vazifalar ro'yxati, vazifa detali va
Boshlash/Stop/Davom ettirish/Yakunlash amallari, ball tarixi.

Har bir yozuv amali mavjud `timer_service`/`task_service`/`penalty_service`
funksiyalarini chaqiradi — chatdagi `handlers/worker/tasks.py` bilan bir xil
kod yo'lidan o'tadi, mantiq ikki marta yozilmagan.
"""

import logging
from datetime import datetime, timezone

from aiohttp import web
from sqlalchemy.exc import IntegrityError

from core.database import async_session
from db.repositories import (
    ClientRepository,
    DepartmentRepository,
    KpiLogRepository,
    TaskAssignmentRepository,
    TaskClaimRepository,
    TaskRepository,
)
from miniapp.util import err, is_mebel_task as _is_mebel_task
from services import (
    claim_service,
    notification_service,
    penalty_service,
    task_service,
    timer_service,
)
from utils.enums import ClaimActionType, TaskStatus, TaskType

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


async def _is_assigned(task_id: int, employee_id: int) -> bool:
    """`common`/`worker` sub-app rolga qarab cheklanmagan (istalgan faol
    xodim uchun ochiq) — shu sabab vazifaga oid har bir amal shu yerda
    xodim haqiqatan HAM o'sha vazifaga (`task_assignments`) biriktirilganini
    tekshirishi SHART, aks holda istalgan xodim istalgan vazifani ko'rishi/
    boshlashi/yakunlashi mumkin bo'lib qolardi."""
    async with async_session() as session:
        assignments = await TaskAssignmentRepository(session).list_by_task(task_id)
    return any(a.employee_id == employee_id for a in assignments)




async def _list_my_tasks(employee_id: int, task_type: TaskType, category: str | None = None) -> list[dict]:
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
            if category and (task.misc_category is None or task.misc_category.value != category):
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
                    "misc_category": task.misc_category.value if task.misc_category else None,
                }
            )
        return items


@routes.get("/tasks")
async def list_tasks(request: web.Request) -> web.Response:
    employee = request["employee"]
    return web.json_response(await _list_my_tasks(employee.id, TaskType.ORDER))


@routes.get("/misctasks")
async def list_misctasks(request: web.Request) -> web.Response:
    """Fasad sex TZ, Phase 9: ixtiyoriy `?category=` filtri — noto'g'ri
    qiymat berilsa (lug'atda yo'q kategoriya) natija shunchaki bo'sh
    ro'yxat bo'ladi, `/leads?brand=`ning filtr naqshi bilan bir xil."""
    employee = request["employee"]
    category = request.query.get("category")
    return web.json_response(await _list_my_tasks(employee.id, TaskType.MISC, category))


@routes.get("/tasks/{task_id}")
async def task_detail(request: web.Request) -> web.Response:
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    if not await _is_assigned(task_id, employee.id):
        return err("not_found", 404)
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            return err("not_found", 404)

        department_name = None
        module = None
        if task.current_department_id is not None:
            department = await DepartmentRepository(session).get_by_id(task.current_department_id)
            department_name = department.name if department else None
            module = department.module if department else None

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
            "module": module,
            "client_name": client_name,
        }
    )


@routes.post("/tasks/{task_id}/start")
async def start_task(request: web.Request) -> web.Response:
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    if not await _is_assigned(task_id, employee.id):
        return err("not_found", 404)
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
    if not await _is_assigned(task_id, employee.id):
        return err("not_found", 404)
    if await _is_mebel_task(task_id):
        return err(
            "Bu bo'lim uchun to'g'ridan-to'g'ri amal endi ishlamaydi — Mini App orqali so'rov yuboring "
            "(Pauza/Yakunlash tugmalari).",
            409,
        )
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
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    if not await _is_assigned(task_id, employee.id):
        return err("not_found", 404)
    if await _is_mebel_task(task_id):
        # Pauza/Yakunlash bilan bir xil qoida: bu modulda ishchi o'zi
        # boshqarmaydi — brigadir so'rov yuboradi, rahbar tasdiqlaydi.
        return err(
            "Mebel bo'limida Davom ettirish endi faqat brigadir orqali yuboriladi.", 409,
        )
    try:
        task = await timer_service.resume_task(task_id, employee.id)
    except timer_service.TaskNotFoundError:
        return err("not_found", 404)
    except timer_service.InvalidTaskStateError as exc:
        return err(str(exc), 409)

    return web.json_response({"id": task.id, "status": task.status.value})


@routes.post("/tasks/{task_id}/finish")
async def finish_task(request: web.Request) -> web.Response:
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    if not await _is_assigned(task_id, employee.id):
        return err("not_found", 404)
    if await _is_mebel_task(task_id):
        return err(
            "Bu bo'lim uchun to'g'ridan-to'g'ri amal endi ishlamaydi — Mini App orqali so'rov yuboring "
            "(Pauza/Yakunlash tugmalari).",
            409,
        )
    try:
        task = await timer_service.finish_task(task_id, employee.id)
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

    await penalty_service.notify_kpi_logs(bot, kpi_logs)

    if task.task_type == TaskType.ORDER:
        # Phase 3 (fork/join): advance_task_stage endi Task | list[Task] | None
        # qaytaradi — fork nuqtasida bir nechta yangi bosqich yaratiladi.
        # `None` ikki ma'no: buyurtma tugadi YOKI join bo'limi qardosh
        # tarmoqlarni kutmoqda — ikkalasida ham yangi bosqich bildirishnomasi
        # yubormaymiz.
        try:
            result = await task_service.advance_task_stage(task.id)
        except Exception:
            logger.exception("advance_task_stage xatosi (task_id=%s)", task.id)
            result = None

        if result is None:
            new_tasks = []
        elif isinstance(result, list):
            new_tasks = result
        else:
            new_tasks = [result]

        if result is not None:
            # `result is None` means either the order is fully terminal or a
            # join is still waiting on sibling branches — "bosqich o'tdi" would
            # be misleading in both cases, so skip the client notification.
            try:
                await notification_service.notify_client_stage_advanced(bot, task.id)
            except Exception:
                logger.exception("notify_client_stage_advanced xatosi (task_id=%s)", task.id)

        for next_task in new_tasks:
            try:
                await notification_service.notify_stage_pending_setup(bot, next_task.id)
            except Exception:
                logger.exception("notify_stage_pending_setup xatosi (task_id=%s)", next_task.id)

    return web.json_response({"id": task.id, "status": task.status.value})


@routes.post("/tasks/{task_id}/pause-claim")
async def submit_pause_claim(request: web.Request) -> web.Response:
    """Mebel moduli: "Pauza" bosish endi darhol amalga oshmaydi — so'rov
    (claim) yaratadi, rahbar tasdiqlaguncha vazifa ACTIVE holatida qoladi
    (`services/claim_service.py`ga qarang)."""
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    if not await _is_assigned(task_id, employee.id):
        return err("not_found", 404)
    if await _is_mebel_task(task_id):
        return err(
            "Mebel bo'limida Pauza/Yakunlash endi faqat brigadir orqali yuboriladi.", 409,
        )
    body = await request.json()
    reason = (body.get("reason") or "").strip()

    try:
        claim = await claim_service.submit_claim(
            task_id, employee.id, ClaimActionType.PAUSE, datetime.now(timezone.utc), reason=reason,
        )
    except claim_service.ClaimAlreadyPendingError as exc:
        return err(str(exc), 409)
    except IntegrityError:
        # Check-then-create race: two near-simultaneous requests both pass the
        # ClaimAlreadyPendingError check above, second insert hits the partial
        # unique index — same 409 outcome as the check catching it cleanly.
        return err("Bu vazifa uchun allaqachon so'rov yuborilgan", 409)
    except ValueError as exc:
        return err(str(exc))

    try:
        await notification_service.notify_claim_submitted(request.config_dict["bot"], claim.id)
    except Exception:
        logger.exception("notify_claim_submitted xatosi (claim_id=%s)", claim.id)

    return web.json_response({"id": claim.id, "status": claim.status.value})


@routes.post("/tasks/{task_id}/finish-claim")
async def submit_finish_claim(request: web.Request) -> web.Response:
    """Mebel moduli: "Yakunlash" bosish endi darhol amalga oshmaydi — so'rov
    yaratadi, rahbar tasdiqlaguncha vazifa ACTIVE holatida qoladi va ball
    hisoblanmaydi."""
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    if not await _is_assigned(task_id, employee.id):
        return err("not_found", 404)
    if await _is_mebel_task(task_id):
        return err(
            "Mebel bo'limida Pauza/Yakunlash endi faqat brigadir orqali yuboriladi.", 409,
        )

    try:
        claim = await claim_service.submit_claim(
            task_id, employee.id, ClaimActionType.FINISH, datetime.now(timezone.utc),
        )
    except claim_service.ClaimAlreadyPendingError as exc:
        return err(str(exc), 409)
    except IntegrityError:
        # Check-then-create race: two near-simultaneous requests both pass the
        # ClaimAlreadyPendingError check above, second insert hits the partial
        # unique index — same 409 outcome as the check catching it cleanly.
        return err("Bu vazifa uchun allaqachon so'rov yuborilgan", 409)

    try:
        await notification_service.notify_claim_submitted(request.config_dict["bot"], claim.id)
    except Exception:
        logger.exception("notify_claim_submitted xatosi (claim_id=%s)", claim.id)

    return web.json_response({"id": claim.id, "status": claim.status.value})


@routes.get("/tasks/{task_id}/claim-status")
async def claim_status(request: web.Request) -> web.Response:
    """Mebel moduli: frontend shu orqali "hozir PENDING so'rov bormi"ni
    tekshiradi (bo'lsa, Pauza/Yakunlash tugmalari o'rniga kutish holati
    ko'rsatiladi)."""
    employee = request["employee"]
    task_id = int(request.match_info["task_id"])
    if not await _is_assigned(task_id, employee.id):
        return err("not_found", 404)

    async with async_session() as session:
        claim = await TaskClaimRepository(session).get_pending_for_task(task_id)

    if claim is None:
        return web.json_response({"pending_claim": None})
    return web.json_response(
        {
            "pending_claim": {
                "id": claim.id,
                "action_type": claim.action_type.value,
                "claimed_at": claim.claimed_at.isoformat(),
            }
        }
    )


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
