"""Rahbar/Nazoratchi ekranlari: dashboard, yangi vazifa, xodimlar. Ruxsat:
faqat Role.ADMIN/Role.SUPERVISOR (`server.py`da route bo'yicha
`require_roles` orqali ulanadi)."""

import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from aiogram.types import BufferedInputFile
from aiohttp import web

from core.database import async_session
from db.repositories import (
    BrigadeRepository,
    DepartmentForkTargetRepository,
    DepartmentRepository,
    EmployeeRepository,
    PenaltyRuleRepository,
    TaskAssignmentRepository,
    TaskClaimRepository,
    TaskRepository,
)
from config import settings
from jobs import reminder_job, report_job
from miniapp.util import current_module, err, in_module, module_scope
from services import (
    claim_service,
    client_service,
    employee_service,
    notification_service,
    penalty_service,
    settings_service,
    stats_service,
    task_service,
)
from trello.client import TrelloAPIError, TrelloClient
from utils.enums import MiscCategory, Role, TaskStatus, TaskType
from utils.formatters import ROLE_LABELS
from utils.modules import MEBEL, NAZORAT_TRELLO

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)


def _department_scope_ok(request: web.Request, target_department_id: int | None) -> bool:
    """ADMIN hammasini ko'radi/boshqaradi. SUPERVISOR faqat O'Z bo'limidagi
    xodim/vazifalarga ruxsat oladi (bo'limi yo'q SUPERVISOR — cheklovsiz,
    `miniapp/api/brigadier.py`'s `_employee_in_scope`/`_resolve_brigade`dagi
    bilan bir xil qoida) — 2026-07-22 auditda topilgan, bo'lim bo'yicha
    cheklanmagan nazoratchi ruxsatini yopadi."""
    employee = request["employee"]
    if employee.role != Role.SUPERVISOR or employee.department_id is None:
        return True
    return target_department_id == employee.department_id


async def _active_brigadier_ids(session, brigades) -> set[int]:
    """`GET /departments/{id}/brigadiers` faqat FAOL brigadirlarni
    ro'yxatga chiqaradi — vazifa tayinlashni tekshiruvchi validatsiya ham
    shu bilan bir xil bo'lishi kerak, aks holda deaktivlashtirilgan
    brigadirga (masalan eskirgan frontend keshi orqali) baribir vazifa
    berib qo'yish mumkin bo'lardi.

    Rol ham tekshiriladi: brigadirlikdan ishchilikka tushirilgan odam
    brigadaning `brigadier_id`sida qolib ketgan bo'lsa (eski ma'lumot yoki
    web-panel orqali kiritilgan xodim), u brigadir sifatida ko'rsatilmasin."""
    employee_repo = EmployeeRepository(session)
    ids: set[int] = set()
    for brigade in brigades:
        if brigade.brigadier_id is None:
            continue
        brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
        if brigadier is not None and brigadier.is_active and brigadier.role == Role.BRIGADIER:
            ids.add(brigadier.id)
    return ids


@routes.get("/dashboard")
async def dashboard(request: web.Request) -> web.Response:
    stats = await stats_service.get_monthly_stats(module=current_module(request))
    active_employees = len(stats)
    completed_total = sum(s.completed_tasks for s in stats)
    # O'rtacha ball/yetakchi faqat KPI oladigan rollardan (rahbar/nazoratchi/
    # sotuvchida ball yo'q — aralashtirilsa o'rtacha sun'iy pasayadi).
    kpi_stats = [s for s in stats if s.role in stats_service.KPI_ROLES]
    avg_score = round(sum(s.total_score for s in kpi_stats) / len(kpi_stats)) if kpi_stats else 0
    top = max(kpi_stats, key=lambda s: s.total_score, default=None)

    return web.json_response(
        {
            "active_employees": active_employees,
            "completed_this_month": completed_total,
            "avg_score": avg_score,
            "top_performer": top.full_name if top and top.total_score > 0 else None,
        }
    )


@routes.get("/departments")
async def list_departments(request: web.Request) -> web.Response:
    async with async_session() as session:
        departments = await DepartmentRepository(session).list_all()
        scope = await module_scope(request, session)
    departments = [d for d in departments if in_module(scope, d.id)]
    return web.json_response(
        [
            {
                "id": d.id,
                "name": d.name,
                "trello_list_id": d.trello_list_id,
                "module": d.module,
                "next_department_id": d.next_department_id,
                "auto_reassign_after_48h": d.auto_reassign_after_48h,
                "starts_stopped": d.starts_stopped,
                "stopped_auto_resume_after_hours": d.stopped_auto_resume_after_hours,
                "requires_join": d.requires_join,
                "factory_name": d.factory_name,
                "stop_target_list_id": d.stop_target_list_id,
                "default_sla_hours": d.default_sla_hours,
                "daily_quota_orders": d.daily_quota_orders,
                "sla_urgent_hours": d.sla_urgent_hours,
                "sla_over_quota_hours": d.sla_over_quota_hours,
                "sla_block_id": d.sla_block_id,
                "telegram_chat_id": d.telegram_chat_id,
            }
            for d in departments
        ]
    )


@routes.post("/departments")
async def create_department(request: web.Request) -> web.Response:
    """Fasad sex TZ: bo'lim CRUD'ining birinchi qismi — hozirgacha
    `departments` qatori faqat bir martalik seed skript orqali yaratilar edi."""
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        return err("name majburiy")

    async with async_session() as session:
        repo = DepartmentRepository(session)
        department = await repo.create(
            name=name,
            module=body.get("module", MEBEL),
            trello_list_id=body.get("trello_list_id"),
            auto_reassign_after_48h=bool(body.get("auto_reassign_after_48h", False)),
            starts_stopped=bool(body.get("starts_stopped", False)),
            factory_name=body.get("factory_name"),
        )
        await session.commit()

    return web.json_response(
        {
            "id": department.id,
            "name": department.name,
            "module": department.module,
            "next_department_id": department.next_department_id,
            "auto_reassign_after_48h": department.auto_reassign_after_48h,
            "starts_stopped": department.starts_stopped,
            "requires_join": department.requires_join,
            "factory_name": department.factory_name,
        },
        status=201,
    )


# Qisman yangilash uchun ruxsat etilgan maydonlar — keyingi fazalar (fork/
# join, factory) shu ro'yxatga qo'shimcha qiladi, shuning uchun oddiy
# ro'yxat/tsikl sifatida saqlanadi (hardcoded pozitsion tuzilma emas).
DEPARTMENT_UPDATABLE_FIELDS = (
    "name",
    "trello_list_id",
    "auto_reassign_after_48h",
    "starts_stopped",
    "factory_name",
    "requires_join",
    "stop_target_list_id",
    "stopped_auto_resume_after_hours",
    "default_sla_hours",  # SPEC.md §5.1
    "daily_quota_orders",  # SPEC.md §5.2
    "sla_urgent_hours",
    "sla_over_quota_hours",
    "sla_block_id",  # SPEC.md §5.3
    "telegram_chat_id",  # SPEC.md §8
)


@routes.delete("/departments/{department_id}")
async def delete_department(request: web.Request) -> web.Response:
    """SPEC.md §10: "Sexlarni yaratish/o'chirish".

    O'chirish FAQAT bo'lim butunlay bo'sh bo'lganda mumkin — unga bog'langan
    vazifa, xodim, brigada yoki uni ko'rsatuvchi zanjir/fork bo'lmasa.
    Kaskad qilib o'chirish ATAYLAB QILINMAGAN: bitta bo'limni o'chirish
    yillik KPI tarixini va tugallangan buyurtmalarni olib ketardi. Band
    bo'lim uchun 409 va aniq sabab qaytariladi — admin avval xodimlarni
    ko'chirishi kerak."""
    department_id = int(request.match_info["department_id"])
    if not _department_scope_ok(request, department_id):
        return err("bu bo'lim sizning doirangizda emas", 403)

    async with async_session() as session:
        repo = DepartmentRepository(session)
        department = await repo.get_by_id(department_id)
        if department is None:
            return err("not_found", 404)

        blockers = []
        if await TaskRepository(session).count_by_department(department_id):
            blockers.append("vazifalar")
        if await EmployeeRepository(session).list_by_department(department_id):
            blockers.append("xodimlar")
        if await BrigadeRepository(session).list_by_department(department_id):
            blockers.append("brigadalar")
        # Zanjirda oldingi bo'lim sifatida ko'rsatilgan bo'lsa ham o'chirilmaydi —
        # aks holda `next_department_id` osilib qolardi (FK NULL emas, mavjud
        # id'ga ishora qiladi).
        if await repo.list_referencing_as_next(department_id):
            blockers.append("zanjir")
        fork_repo = DepartmentForkTargetRepository(session)
        if await fork_repo.list_by_department(department_id) or await fork_repo.list_by_target_department(department_id):
            blockers.append("fork")

        if blockers:
            return err(f"bo'lim bo'sh emas ({', '.join(blockers)}) — avval ularni ko'chiring", 409)

        await repo.delete(department)
        await session.commit()

    return web.json_response({"deleted": True})


@routes.post("/departments/{department_id}")
async def update_department(request: web.Request) -> web.Response:
    """Qisman yangilash: so'rov tanasida FAQAT kelgan maydonlar yoziladi
    (`toggle_autoreassign` bilan bir xil session/commit naqshi)."""
    department_id = int(request.match_info["department_id"])
    if not _department_scope_ok(request, department_id):
        return err("bu bo'lim sizning doirangizda emas", 403)
    body = await request.json()

    updates = {}
    for field in DEPARTMENT_UPDATABLE_FIELDS:
        if field in body:
            updates[field] = body[field]
    if "name" in updates and not (updates["name"] or "").strip():
        return err("name bo'sh bo'lishi mumkin emas")

    async with async_session() as session:
        repo = DepartmentRepository(session)
        department = await repo.get_by_id(department_id)
        if department is None:
            return err("not_found", 404)
        if updates:
            await repo.update(department, **updates)
            await session.commit()

    return web.json_response(
        {
            "id": department.id,
            "name": department.name,
            "trello_list_id": department.trello_list_id,
            "next_department_id": department.next_department_id,
            "auto_reassign_after_48h": department.auto_reassign_after_48h,
            "starts_stopped": department.starts_stopped,
            "stopped_auto_resume_after_hours": department.stopped_auto_resume_after_hours,
            "requires_join": department.requires_join,
            "factory_name": department.factory_name,
            "stop_target_list_id": department.stop_target_list_id,
            "default_sla_hours": department.default_sla_hours,
            "daily_quota_orders": department.daily_quota_orders,
            "sla_urgent_hours": department.sla_urgent_hours,
            "sla_over_quota_hours": department.sla_over_quota_hours,
            "sla_block_id": department.sla_block_id,
            "telegram_chat_id": department.telegram_chat_id,
        }
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


@routes.get("/departments/{department_id}/fork-targets")
async def list_fork_targets(request: web.Request) -> web.Response:
    """Fasad sex Phase 3: shu fork nuqtasidan chiqadigan parallel tarmoq
    bo'limlari ro'yxati (ism bilan)."""
    department_id = int(request.match_info["department_id"])
    if not _department_scope_ok(request, department_id):
        return err("not_found", 404)
    async with async_session() as session:
        fork_repo = DepartmentForkTargetRepository(session)
        dept_repo = DepartmentRepository(session)
        rows = await fork_repo.list_by_department(department_id)
        items = []
        for row in rows:
            target = await dept_repo.get_by_id(row.target_department_id)
            items.append(
                {
                    "target_department_id": row.target_department_id,
                    "target_department_name": target.name if target else None,
                }
            )
    return web.json_response(items)


@routes.post("/departments/{department_id}/fork-targets")
async def set_fork_targets(request: web.Request) -> web.Response:
    """Fasad sex Phase 3: fork nuqtasi tarmoqlarini TO'LIQ ALMASHTIRISH
    (delegate_task/reassign_task_brigade'dagi "hammasini o'chir, yangisini
    qo'sh" naqshi bilan bir xil)."""
    department_id = int(request.match_info["department_id"])
    if not _department_scope_ok(request, department_id):
        return err("bu bo'lim sizning doirangizda emas", 403)
    body = await request.json()
    try:
        target_ids = [int(t) for t in (body.get("target_department_ids") or [])]
    except (TypeError, ValueError):
        return err("target_department_ids noto'g'ri")
    if department_id in target_ids:
        return err("bo'lim o'zini o'ziga fork qila olmaydi")

    async with async_session() as session:
        dept_repo = DepartmentRepository(session)
        fork_repo = DepartmentForkTargetRepository(session)
        if await dept_repo.get_by_id(department_id) is None:
            return err("not_found", 404)
        for tid in target_ids:
            if await dept_repo.get_by_id(tid) is None:
                return err(f"target_department_id {tid} topilmadi")
        for row in await fork_repo.list_by_department(department_id):
            await fork_repo.delete(row)
        for tid in target_ids:
            await fork_repo.create(department_id=department_id, target_department_id=tid)
        await session.commit()

    return web.json_response(
        {"department_id": department_id, "target_department_ids": [int(t) for t in target_ids]}
    )


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
    caller = request["employee"]
    if caller.role == Role.SUPERVISOR and caller.department_id is not None:
        department_id = caller.department_id
    async with async_session() as session:
        repo = BrigadeRepository(session)
        brigades = (
            await repo.list_by_department(int(department_id)) if department_id else await repo.list_all()
        )
        scope = await module_scope(request, session)
    brigades = [b for b in brigades if in_module(scope, b.department_id)]
    return web.json_response([{"id": b.id, "name": b.name} for b in brigades])


@routes.get("/departments/{department_id}/brigadiers")
async def list_department_brigadiers(request: web.Request) -> web.Response:
    """Yangi vazifa/bosqich uchun: rahbar bo'limni tanlagach, faqat SHU
    bo'limdagi brigadalarning brigadirlari (ism-familiyasi bilan) ko'rsatiladi
    — endi vazifa to'g'ridan-to'g'ri xodimga emas, brigadirga beriladi,
    brigadir esa Mini App'da o'z brigadasidagi xodimga topshiradi."""
    department_id = int(request.match_info["department_id"])
    if not _department_scope_ok(request, department_id):
        return err("not_found", 404)
    async with async_session() as session:
        brigades = await BrigadeRepository(session).list_by_department(department_id)
        employee_repo = EmployeeRepository(session)
        items = []
        for brigade in brigades:
            if brigade.brigadier_id is None:
                continue
            brigadier = await employee_repo.get_by_id(brigade.brigadier_id)
            if brigadier is None or not brigadier.is_active or brigadier.role != Role.BRIGADIER:
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
    if not _department_scope_ok(request, int(department_id)):
        return err("bu bo'lim sizning doirangizda emas", 403)

    async with async_session() as session:
        target_department = await DepartmentRepository(session).get_by_id(int(department_id))
    if target_department is not None and target_department.module == MEBEL:
        return err("Bu bo'lim uchun buyurtmalar endi faqat Trello orqali yaratiladi", 409)

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

    seller_ids = [int(s) for s in (body.get("seller_ids") or [])]

    try:
        task = await task_service.create_task(
            title=title,
            description=body.get("description"),
            deadline=deadline,
            department_id=int(department_id),
            employee_ids=[int(brigadier_id)],
            client_id=client_id,
            created_by_employee_id=request["employee"].id,
            seller_ids=seller_ids,
            is_urgent=bool(body.get("is_urgent", False)),  # SPEC.md §5.2
        )
    except task_service.DepartmentNotFoundError:
        return err("bo'lim topilmadi", 404)
    except task_service.DepartmentNotConfiguredError as exc:
        return err(str(exc), 409)
    except ValueError as exc:
        return err(str(exc))

    return web.json_response({"id": task.id, "status": task.status.value}, status=201)


@routes.get("/employees")
async def list_employees(request: web.Request) -> web.Response:
    department_id = request.query.get("department_id")
    caller = request["employee"]
    # SUPERVISOR-bo'limli chaqiruvchi uchun natija doim O'Z bo'limi bilan
    # cheklanadi — `department_id` so'rov parametri orqali boshqa bo'limni
    # so'rab bo'lmaydi (ilgari cheklovsiz edi).
    if caller.role == Role.SUPERVISOR and caller.department_id is not None:
        department_id = caller.department_id

    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        department_repo = DepartmentRepository(session)

        employees = (
            await employee_repo.list_by_department(int(department_id))
            if department_id
            else await employee_repo.list_all()
        )
        departments = {d.id: d.name for d in await department_repo.list_all()}
        scope = await module_scope(request, session)
    employees = [e for e in employees if in_module(scope, e.department_id)]

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
        if employee is None or not _department_scope_ok(request, employee.department_id):
            return err("not_found", 404)
        department = (
            await DepartmentRepository(session).get_by_id(employee.department_id)
            if employee.department_id
            else None
        )
        brigade_repo = BrigadeRepository(session)
        brigade = await brigade_repo.get_by_id(employee.brigade_id) if employee.brigade_id else None
        # Rahbarlik qiladigan bo'limlar alohida ustunda emas — brigadalar
        # orqali ifodalanadi (brigada = brigadir, `employee_service`ga qarang).
        led_department_ids = [b.department_id for b in await brigade_repo.list_by_brigadier_id(employee.id)]

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
            "led_department_ids": led_department_ids,
            "manager_id": employee.manager_id,  # SPEC.md §7/§8
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
    async with async_session() as session:
        target = await EmployeeRepository(session).get_by_id(employee_id)
    if target is None or not _department_scope_ok(request, target.department_id):
        return err("not_found", 404)

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
    if "manager_id" in body:
        # SPEC.md §7/§8: bevosita rahbar. O'z-o'ziga ishora qilish halqa
        # yaratadi (`_add_managers` cheksiz aylanmaydi, chunki bir pog'ona
        # o'qiydi — lekin baribir ma'nosiz), shuning uchun rad etiladi.
        manager_id = body["manager_id"]
        if manager_id is not None and int(manager_id) == employee_id:
            return err("xodim o'ziga rahbar bo'la olmaydi")
        fields["manager_id"] = int(manager_id) if manager_id else None
    if "brigade_id" in body:
        fields["brigade_id"] = body["brigade_id"]
    elif "department_id" in body:
        # bo'lim o'zgarganda eski brigada mos kelmasligi mumkin (chat bilan bir xil qoida)
        fields["brigade_id"] = None

    # Qo'shimcha rahbarlik bo'limlari (masalan Kraska brigadiri Shkurkaga ham
    # qarasa) — har biri uchun brigada avtomatik yaratiladi/biriktiriladi.
    led_department_ids = None
    if "led_department_ids" in body:
        led_department_ids = [int(d) for d in (body["led_department_ids"] or [])]
        for department_id in led_department_ids:
            if not _department_scope_ok(request, department_id):
                return err("bu bo'lim sizning doirangizda emas", 403)

    if not fields and led_department_ids is None:
        return err("hech qanday maydon berilmadi")

    try:
        employee = await employee_service.update_employee(
            employee_id, led_department_ids=led_department_ids, **fields
        )
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
    if employee is None or not _department_scope_ok(request, employee.department_id):
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

    category_value = body.get("category") or None
    if category_value is not None and category_value not in {c.value for c in MiscCategory}:
        return err("category noto'g'ri")
    category = MiscCategory(category_value) if category_value else None

    try:
        task = await task_service.create_misc_task(
            text=text, deadline=deadline, employee_ids=[int(e) for e in employee_ids], category=category
        )
    except ValueError as exc:
        return err(str(exc), 409)

    try:
        await notification_service.notify_task_started(request.config_dict["bot"], task.id)
    except Exception:
        logger.exception("notify_task_started xatosi (task_id=%s)", task.id)

    return web.json_response({"id": task.id, "title": task.title}, status=201)


@routes.get("/misctasks")
async def list_admin_misctasks(request: web.Request) -> web.Response:
    """Fasad sex TZ, Phase 9 tuzatish: worker-scoped `GET /misctasks`dan
    farqli, HAR BIR MISC vazifani ko'rsatadi (kimga biriktirilganidan
    qat'i nazar) — shu kamchilikni yopish uchun qo'shildi (mustaqil sharh:
    admin bo'lim filtri mavjud edi, lekin MISC vazifalarni butunlay ko'ra
    olmasdi). Ixtiyoriy `?category=` filtri, `list_misctasks`dagi bilan bir
    xil naqsh: lug'atda yo'q qiymat berilsa — bo'sh ro'yxat."""
    category_value = request.query.get("category")
    category = None
    if category_value:
        if category_value not in {c.value for c in MiscCategory}:
            return web.json_response([])
        category = MiscCategory(category_value)

    async with async_session() as session:
        tasks = await TaskRepository(session).list_by_type(TaskType.MISC, misc_category=category)
        tasks = [t for t in tasks if _department_scope_ok(request, t.current_department_id)]

        assignment_repo = TaskAssignmentRepository(session)
        # Xodim ismlari bir marta yuklanadi: ilgari har biriktirish uchun
        # alohida `get_by_id()` ketardi (vazifa x biriktirish = N*M so'rov).
        # Xodimlar soni bu tashkilotda yuzlab — bitta ro'yxat arzon.
        employees = {e.id: e for e in await EmployeeRepository(session).list_all()}
        scope = await module_scope(request, session)
        items = []
        for task in tasks:
            assignments = await assignment_repo.list_by_task(task.id)
            assignees = [employees[a.employee_id] for a in assignments if a.employee_id in employees]
            # MISC vazifada bo'lim umuman yo'q (`create_misc_task` uni
            # so'ramaydi) — modul chegarasi shu sabab BIRIKTIRILGAN XODIM
            # bo'limidan olinadi, vazifanikidan emas.
            if scope is not None and not any(in_module(scope, e.department_id) for e in assignees):
                continue
            names = [e.full_name for e in assignees]
            items.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status.value,
                    "deadline": task.deadline.isoformat() if task.deadline else None,
                    "misc_category": task.misc_category.value if task.misc_category else None,
                    "assigned_employee_names": names,
                }
            )
    return web.json_response(items)


@routes.get("/stats")
async def full_stats(request: web.Request) -> web.Response:
    """10-band: `/stats`ning to'liq versiyasi — dashboard'dagi xulosa
    tile'laridan farqli, har bir xodim bo'yicha to'liq saralangan jadval.
    Faqat KPI oladigan rollar (ishchi/brigadir) — rahbar/nazoratchi/sotuvchida
    ball umuman bo'lmagani uchun ro'yxatga qo'shilmaydi. Ixtiyoriy
    `?factory_name=` query parametri (Fasad sex TZ §9) natijani shu zavodga
    tegishli bo'limlardagi xodimlar bilan cheklaydi — berilmasa, avvalgidek
    filtrsiz."""
    factory_name = request.query.get("factory_name") or None
    since, until = _period_from_query(request)
    stats = sorted(
        (
            s
            for s in await stats_service.get_monthly_stats(
                factory_name=factory_name, since=since, until=until, module=current_module(request)
            )
            if s.role in stats_service.KPI_ROLES
        ),
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
                "avg_completion_hours": s.avg_completion_hours,  # SPEC.md §11
            }
            for s in stats
        ]
    )


@routes.get("/stats/capacity")
async def capacity_stats(request: web.Request) -> web.Response:
    """Fasad sex TZ, Phase 6: kunlik norma (5 punkt/ishchi) — bo'lim uchun
    reja (`planned_points`) va bajarilgan vazifa soni (`actual_points`,
    PROKSI, haqiqiy kv.m emas) yonma-yon. `?department_id=` majburiy;
    `?since=`/`?until=` ixtiyoriy ISO 8601 (ikkalasi birga berilishi kerak,
    aks holda ikkalasi ham joriy oyga tushadi — `penalty_service.month_bounds`
    bilan bir xil qoida)."""
    department_id = request.query.get("department_id")
    if not department_id:
        return err("department_id majburiy")
    try:
        department_id = int(department_id)
    except ValueError:
        return err("department_id noto'g'ri")
    if not _department_scope_ok(request, department_id):
        return err("bu bo'lim sizning doirangizda emas", 403)

    since_raw = request.query.get("since")
    until_raw = request.query.get("until")
    if since_raw and until_raw:
        try:
            since = datetime.fromisoformat(since_raw)
            until = datetime.fromisoformat(until_raw)
        except ValueError:
            return err("since/until ISO 8601 formatida bo'lishi kerak")
    else:
        since, until = penalty_service.month_bounds(datetime.now(timezone.utc))

    capacity = await stats_service.get_capacity_vs_actual(department_id, since, until)
    return web.json_response(
        {
            "worker_count": capacity.worker_count,
            "planned_points": capacity.planned_points,
            "actual_points": capacity.actual_points,
        }
    )


def _period_from_query(request: web.Request) -> tuple[datetime, datetime]:
    """SPEC.md §11 "davr bo'yicha filtr": `?since=`/`?until=` (ISO 8601,
    ikkalasi birga). Berilmasa joriy oy — `capacity_stats` bilan bir xil
    qoida. Noto'g'ri format ham jimgina joriy oyga tushadi: bular faqat
    ko'rsatkich ekranlari, yarim to'ldirilgan sana kiritish xato
    qaytarishga arzimaydi."""
    since_raw = request.query.get("since")
    until_raw = request.query.get("until")
    if since_raw and until_raw:
        try:
            return datetime.fromisoformat(since_raw), datetime.fromisoformat(until_raw)
        except ValueError:
            pass
    return penalty_service.month_bounds(datetime.now(timezone.utc))


@routes.get("/stopped-orders")
async def stopped_orders(request: web.Request) -> web.Response:
    """SPEC.md §6: ""STOP bosilgan zakazlar" degan alohida ro'yxat/filtr
    bo'ladi" — hozir to'xtatilgan buyurtmalar, eng uzoq turganidan boshlab."""
    orders = await stats_service.get_stopped_orders(module=request.query.get("module", NAZORAT_TRELLO))
    return web.json_response(
        [
            {
                "task_id": o.task_id,
                "title": o.title,
                "department": o.department_name,
                "reason": o.reason,
                "stopped_at": o.stopped_at.isoformat(),
                "stopped_hours": o.stopped_hours,
            }
            for o in orders
        ]
    )


@routes.get("/stats/funnel")
async def funnel_stats(request: web.Request) -> web.Response:
    """SPEC.md §11: "zakazlar voronkasi — qaysi bosqichda nechta zakaz
    turibdi". Davr filtri YO'Q — bu hozirgi holat kesimi, tarix emas."""
    stages = await stats_service.get_order_funnel(module=request.query.get("module", NAZORAT_TRELLO))
    return web.json_response(
        [
            {
                "department_id": s.department_id,
                "department": s.department_name,
                "pending_setup": s.pending_setup,
                "active": s.active,
                "stopped": s.stopped,
                "overdue": s.overdue,
                "total": s.total,
            }
            for s in stages
            if _department_scope_ok(request, s.department_id)
        ]
    )


@routes.get("/stats/bottlenecks")
async def bottleneck_stats(request: web.Request) -> web.Response:
    """SPEC.md §11: "har bir bosqich: o'rtacha davomiylik vs reja" — eng
    sekinidan boshlab. Davomiylikdan STOP vaqti chiqarib tashlangan (§6)."""
    since, until = _period_from_query(request)
    stages = await stats_service.get_stage_bottlenecks(
        since, until, module=request.query.get("module", NAZORAT_TRELLO)
    )
    return web.json_response(
        [
            {
                "department_id": s.department_id,
                "department": s.department_name,
                "completed_tasks": s.completed_tasks,
                "avg_hours": s.avg_hours,
                "planned_hours": s.planned_hours,
            }
            for s in stages
            if _department_scope_ok(request, s.department_id)
        ]
    )


@routes.get("/stats/stops")
async def stop_stats(request: web.Request) -> web.Response:
    """SPEC.md §11: "STOP statistikasi: nechta zakaz, qancha vaqt, sabablari"."""
    since, until = _period_from_query(request)
    stats = await stats_service.get_stop_stats(
        since, until, module=request.query.get("module", NAZORAT_TRELLO)
    )
    return web.json_response(
        {
            "stop_count": stats.stop_count,
            "task_count": stats.task_count,
            "total_hours": stats.total_hours,
            "reasons": [{"reason": reason, "count": count} for reason, count in stats.reasons],
        }
    )


@routes.post("/stats/export")
async def export_stats(request: web.Request) -> web.Response:
    """SPEC.md §11 "Excel'ga eksport" — CSV sifatida (Excel uni to'g'ridan-
    to'g'ri ochadi, yangi bog'liqlik kerak emas).

    Fayl HTTP javobida QAYTARILMAYDI, balki so'rovchining o'z Telegram
    chatiga hujjat sifatida yuboriladi. Sabab: har bir so'rov
    `X-Telegram-Init-Data` sarlavhasini talab qiladi, ya'ni oddiy `<a
    download>` havolasi ishlamaydi, blob orqali yuklab olish esa Telegram
    WebView'da ishonchsiz. Hujjat sifatida yuborish — nativ va ishonchli
    yo'l, foydalanuvchi faylni chatidan istalgan vaqtda ocha oladi.

    BOM (`\\ufeff`) bilan boshlanadi: usiz Excel UTF-8ni tanimay, o'zbekcha
    apostrof va kirill harflarni buzib ko'rsatadi."""
    since, until = _period_from_query(request)
    factory_name = request.query.get("factory_name") or None
    stats = sorted(
        (
            s
            # `since`/`until` ham uzatiladi: ilgari ular faqat fayl nomi va
            # izohga tushardi, CSV ichi esa doim JORIY oy bo'lib qolardi.
            for s in await stats_service.get_monthly_stats(
                factory_name=factory_name, since=since, until=until, module=current_module(request)
            )
            if s.role in stats_service.KPI_ROLES
        ),
        key=lambda s: s.total_score,
        reverse=True,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")  # Excel (ru/uz lokal) `;` kutadi
    writer.writerow(
        ["Xodim", "Rol", "Bajarilgan", "Jami ball", "Jarimalar soni", "O'rtacha bajarish (soat)"]
    )
    for s in stats:
        writer.writerow([
            s.full_name, ROLE_LABELS.get(s.role, s.role.value), s.completed_tasks,
            s.total_score, s.penalty_count, s.avg_completion_hours,
        ])

    employee = request["employee"]
    if employee.telegram_id is None:
        return err("Telegram hisobingiz ulanmagan — faylni yuborib bo'lmadi")

    filename = f"statistika-{since:%Y-%m-%d}.csv"
    # `request.config_dict` — `request.app` EMAS: `bot` faqat ildiz ilovada
    # saqlanadi va aiohttp uni sub-app'larga tarqatmaydi (CLAUDE.md).
    bot = request.config_dict["bot"]
    try:
        await bot.send_document(
            employee.telegram_id,
            BufferedInputFile(("﻿" + buffer.getvalue()).encode("utf-8"), filename=filename),
            caption=f"📊 Statistika: {since:%d.%m.%Y} — {until:%d.%m.%Y}",
        )
    except Exception:
        logger.exception("export_stats: CSV yuborilmadi (employee_id=%s)", employee.id)
        return err("fayl yuborilmadi, keyinroq urinib ko'ring", 502)

    return web.json_response({"sent": True, "rows": len(stats), "filename": filename})


_SETTING_FIELDS = list(settings_service.AppSettingsSnapshot.__dataclass_fields__)
_SETTING_FIELDS = [
    f for f in _SETTING_FIELDS if f not in ("reminder_schedule", "sales_board_lists")
]


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
        "plus_ball_per_day", "plus_ball_max_days",
        "lead_follow_up_threshold_days", "daily_quota_points_per_worker",
        "deadline_warning_hours",  # SPEC.md §5.4
    ):
        value = int(value)
        if value <= 0:
            raise ValueError
    elif field == "overdue_repeat_hours":
        # SPEC.md §5.4: 0 = takroriy eslatma o'chirilgan (yuqoridagilardan
        # farqli, bu yerda nol haqiqiy va foydali qiymat).
        value = int(value)
        if value < 0:
            raise ValueError
    elif field == "penalize_all_assignees":  # SPEC.md §7
        value = bool(value)
    elif field == "report_time":
        settings_service.validate_time_str(value)
    else:
        raise ValueError(f"noma'lum sozlama: {field}")
    return value


def _serialize_setting(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime) else value


@routes.get("/settings")
async def get_settings(request: web.Request) -> web.Response:
    snapshot = await settings_service.get_settings()
    return web.json_response(
        {field: _serialize_setting(getattr(snapshot, field)) for field in _SETTING_FIELDS}
    )


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

    return web.json_response(
        {field: _serialize_setting(getattr(updated, field)) for field in _SETTING_FIELDS}
    )


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
        scope = await module_scope(request, session)
        items = []
        for task in tasks:
            department = (
                await department_repo.get_by_id(task.current_department_id)
                if task.current_department_id
                else None
            )
            if not _department_scope_ok(request, task.current_department_id):
                continue
            if not in_module(scope, task.current_department_id):
                continue
            items.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "department": department.name if department else None,
                    "department_id": task.current_department_id,
                    # SPEC.md §5.1: bo'lim SLA'si muddatni allaqachon
                    # hisoblagan bo'lishi mumkin — Mini App uni oldindan
                    # to'ldirib ko'rsatadi, nazoratchi qayta yozishi shart emas.
                    "deadline": task.deadline.isoformat() if task.deadline else None,
                    "is_urgent": task.is_urgent,  # TZ 2.6
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
    # SPEC.md §5.1: bo'lim `default_sla_hours` sozlagan bo'lsa, muddat
    # bosqich yaratilganda allaqachon hisoblangan — nazoratchi uni qayta
    # kiritishi shart emas (`deadline` yuborilmasa mavjudi saqlanadi).
    deadline = None
    if body.get("deadline"):
        try:
            deadline = datetime.fromisoformat(body["deadline"])
        except ValueError:
            return err("deadline noto'g'ri formatda (ISO 8601 kerak)")
        if deadline <= datetime.now(deadline.tzinfo):
            return err("deadline kelajakda bo'lishi kerak")

    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None or task.current_department_id is None:
            return err("not_found", 404)
        if deadline is None and task.deadline is None:
            return err("deadline majburiy (bu bo'limda standart SLA sozlanmagan)")
        if not _department_scope_ok(request, task.current_department_id):
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


@routes.get("/orders")
async def list_orders(request: web.Request) -> web.Response:
    """TZ 2.3/2.6-band uchun kirish nuqtasi: joriy moduldagi OCHIQ
    buyurtmalar ro'yxati.

    Shu paytgacha rahbar uchun "hamma buyurtma" ekrani umuman yo'q edi —
    faqat "sozlash kutilmoqda" va "ko'rib chiqish kutilmoqda" navbatlari
    bor edi, ya'ni ishlab turgan buyurtmaga (muddat o'zgartirish, srochniy
    qilish) hech qayerdan yetib bo'lmasdi."""
    open_statuses = (
        TaskStatus.PENDING_SETUP, TaskStatus.ACTIVE, TaskStatus.STOPPED, TaskStatus.OVERDUE
    )
    async with async_session() as session:
        task_repo = TaskRepository(session)
        department_repo = DepartmentRepository(session)
        scope = await module_scope(request, session)
        items = []
        for status in open_statuses:
            for task in await task_repo.list_by_status(status):
                if task.task_type != TaskType.ORDER:
                    continue
                if not _department_scope_ok(request, task.current_department_id):
                    continue
                if not in_module(scope, task.current_department_id):
                    continue
                department = (
                    await department_repo.get_by_id(task.current_department_id)
                    if task.current_department_id
                    else None
                )
                items.append(
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status.value,
                        "department": department.name if department else None,
                        "department_id": task.current_department_id,
                        "deadline": task.deadline.isoformat() if task.deadline else None,
                        "is_urgent": task.is_urgent,
                    }
                )

    # Muddati yaqinlari birinchi; muddatsizlari (PENDING_SETUP, SLA yo'q) oxirida.
    items.sort(key=lambda i: (i["deadline"] is None, i["deadline"] or ""))
    return web.json_response(items)


@routes.post("/tasks/{task_id}/deadline")
async def update_task_deadline(request: web.Request) -> web.Response:
    """TZ 2.3-band: "muddatni ortga/oldinga QO'LDA o'zgartirish imkoni".

    Shu paytgacha `tasks.deadline` faqat uch joyda yozilardi — vazifa
    yaratilganda, `PENDING_SETUP` faollashtirilganda va Stop/Resume
    avtomatik siljishida — ya'ni ishlab turgan vazifaning muddatini
    umuman o'zgartirib bo'lmasdi.

    `create_task`dan farqli, bu yerda O'TGAN sana ham qabul qilinadi:
    TZ aynan "ortga ham" deydi (masalan mijoz shoshiltirdi). Bunday holda
    vazifa keyingi soatlik jobda OVERDUE bo'ladi — bu to'g'ri xatti-harakat.

    Uchta yon ta'sir, hammasi ataylab:
    1. `day_left_notified_at`/`last_overdue_reminder_at` NULLga qaytariladi —
       aks holda muddat OLDINGA surilganda "1 kun qoldi" ogohlantirishi
       qayta ishlamasdi (bir marta yuborilgan deb qolardi).
    2. Vazifa OVERDUE bo'lib, yangi muddat kelajakda bo'lsa — ACTIVE'ga
       qaytariladi (`timer_service.reopen_if_owerdue` bilan bir xil mantiq).
    3. Trello kartaning `due`si ham yangilanadi (ikkinchi-darajali).

    Mebel MUZLATILGAN: u yerda muddat Trello kartadan keladi va har 5
    daqiqada qayta o'qiladi — bu yerda yozilgani baribir ustidan yozilardi."""
    task_id = int(request.match_info["task_id"])
    body = await request.json()
    try:
        deadline = datetime.fromisoformat(body["deadline"])
    except (KeyError, TypeError, ValueError):
        return err("deadline noto'g'ri formatda (ISO 8601 kerak)")

    async with async_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        if task is None:
            return err("not_found", 404)
        if not _department_scope_ok(request, task.current_department_id):
            return err("not_found", 404)
        if task.status == TaskStatus.COMPLETED:
            return err("yakunlangan vazifaning muddatini o'zgartirib bo'lmaydi", 409)

        department = (
            await DepartmentRepository(session).get_by_id(task.current_department_id)
            if task.current_department_id is not None
            else None
        )
        if department is not None and department.module == MEBEL:
            return err("Bu bo'limda muddat Trello kartadan boshqariladi", 409)

        old_deadline = task.deadline
        fields = {
            "deadline": deadline,
            "day_left_notified_at": None,
            "last_overdue_reminder_at": None,
        }
        if task.status == TaskStatus.OVERDUE and deadline > datetime.now(timezone.utc):
            fields["status"] = TaskStatus.ACTIVE
        await task_repo.update(task, **fields)
        await session.commit()
        card_id = task.trello_card_id

    # Ball aynan `deadline`dan hisoblanadi, ya'ni bu o'zgarish PUL bilan
    # bog'liq — kim, qachon, nimadan nimaga o'zgartirgani logda qoladi.
    logger.info(
        "Muddat qo'lda o'zgartirildi: task=%s, %s -> %s (kim: employee_id=%s)",
        task_id, old_deadline, deadline, request["employee"].id,
    )

    if card_id:
        try:
            async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
                await trello.set_card_due(card_id, deadline)
        except Exception:
            logger.exception("update_task_deadline: Trello karta muddati yangilanmadi (task=%s)", task_id)

    try:
        await notification_service.notify_deadline_changed(
            request.config_dict["bot"], task_id, old_deadline=old_deadline
        )
    except Exception:
        logger.exception("notify_deadline_changed xatosi (task_id=%s)", task_id)

    return web.json_response({"id": task_id, "deadline": deadline.isoformat(), "status": task.status.value})


@routes.post("/tasks/{task_id}/urgent")
async def set_task_urgent(request: web.Request) -> web.Response:
    """TZ 2.6-band: ""Srochnost" belgisi qo'yilsa — muddat avtomatik tushadi".

    Ilgari `is_urgent` FAQAT buyurtma yaratilayotganda o'qilardi
    (`POST /tasks`), ya'ni allaqachon yo'lda ketayotgan buyurtmani srochniy
    qilib bo'lmasdi — TZ esa aynan shu holatni nazarda tutadi (mijoz
    shoshiltirsa).

    Belgi butun buyurtmaga tegishli, bitta bosqichga emas — shuning uchun u
    `_spawn_pending_stage()` orqali keyingi bosqichlarga o'zi ko'chib boradi
    (SPEC.md §5.2), bu yerda faqat JORIY bosqich-qatori yangilanadi.

    Muddat qayta hisoblanishi: bo'limda `sla_urgent_hours` sozlangan bo'lsa
    `deadline = hozir + shu soat`. Belgi OLIB TASHLANSA muddat tegilmaydi —
    srochniy davrida bajarilgan ishni "endi kechikdingiz" holatiga qaytarish
    ishchini nohaq jazolagan bo'lardi.

    Mebel MUZLATILGAN: u yerda muddat Trello kartadan keladi va har pollda
    qayta o'qiladi, ya'ni bu yerda yozilgan qiymat baribir ustidan yozilardi."""
    task_id = int(request.match_info["task_id"])
    body = await request.json()
    is_urgent = bool(body.get("is_urgent", True))

    async with async_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        if task is None:
            return err("not_found", 404)
        if not _department_scope_ok(request, task.current_department_id):
            return err("not_found", 404)
        if task.status == TaskStatus.COMPLETED:
            return err("yakunlangan vazifani srochniy qilib bo'lmaydi", 409)

        department = (
            await DepartmentRepository(session).get_by_id(task.current_department_id)
            if task.current_department_id is not None
            else None
        )
        if department is not None and department.module == MEBEL:
            return err("Bu bo'limda muddat Trello kartadan boshqariladi", 409)

        fields: dict = {"is_urgent": is_urgent}
        if is_urgent and department is not None and department.sla_urgent_hours:
            fields["deadline"] = datetime.now(timezone.utc) + timedelta(
                hours=department.sla_urgent_hours
            )
        await task_repo.update(task, **fields)
        await session.commit()

    return web.json_response(
        {
            "id": task.id,
            "is_urgent": task.is_urgent,
            "deadline": task.deadline.isoformat() if task.deadline else None,
        }
    )


# ---------- TZ 1.3/8.1-band: jarima jadvali (penalty_rules) ----------
#
# Bu jadval 8.2-bandning o'zagi ("kechikish -> ball"), lekin bugungacha
# HECH QANDAY UI/API'si yo'q edi — faqat to'g'ridan-to'g'ri SQL orqali
# o'zgartirilardi, ya'ni "jarima balli har bosqichga biriktiriladi" talabi
# amalda bajarilmasdi. `department_id IS NULL` — global (zaxira) qoida,
# bo'limga xos qator undan ustun turadi (`penalty_rule_repo.py`).


def _penalty_rule_json(rule, department_name: str | None = None) -> dict:
    return {
        "id": rule.id,
        "department_id": rule.department_id,
        "department_name": department_name,
        "min_hours_late": rule.min_hours_late,
        "max_hours_late": rule.max_hours_late,
        "score": rule.score,
    }


def _global_top_rule_survives(rules, *, changed_id: int, new_max_hours, deleting: bool) -> bool:
    """CLAUDE.md'dagi qat'iy qoida: GLOBAL jadvalda `max_hours_late IS NULL`
    (ochiq yuqori chegara) qatori DOIM bo'lishi kerak.

    Sababi jim va qimmat: `find_applicable_rule()` ataylab "eng yaqin
    bracket"ga yopishib qolmaydi — mos qator topilmasa `None` qaytaradi va
    job yo'llarida bu faqat ogohlantirish logi bo'lib qoladi. Ya'ni ochiq
    qator o'chirilsa, YETARLICHA ko'p kechikkan har qanday vazifa
    UMUMAN jarimasiz o'tib ketadi — xato ham chiqmaydi. Shuning uchun bunday
    tahrir 409 bilan rad etiladi.

    Sof funksiya (bazaga tegmaydi) — `tests/test_penalty_rule_guard.py`."""
    if not deleting and new_max_hours is None:
        return True  # tahrirdan keyin ochiq qator baribir shu qatorning o'zi
    return any(
        r.department_id is None and r.max_hours_late is None and r.id != changed_id for r in rules
    )


def _parse_penalty_rule_body(body: dict) -> tuple[dict, str | None]:
    """(maydonlar, xato matni) — validatsiya API va UI'da takrorlanmasin
    uchun bitta joyda."""
    try:
        min_hours = int(body["min_hours_late"])
        score = int(body["score"])
    except (KeyError, TypeError, ValueError):
        return {}, "min_hours_late va score majburiy (butun son)"

    raw_max = body.get("max_hours_late")
    max_hours = None
    if raw_max not in (None, ""):
        try:
            max_hours = int(raw_max)
        except (TypeError, ValueError):
            return {}, "max_hours_late noto'g'ri"

    if min_hours < 0:
        return {}, "min_hours_late manfiy bo'lishi mumkin emas"
    if max_hours is not None and max_hours <= min_hours:
        return {}, "max_hours_late min_hours_late'dan katta bo'lishi kerak"
    if score == 0:
        return {}, "score 0 bo'lishi mumkin emas"

    department_id = body.get("department_id")
    return (
        {
            "department_id": int(department_id) if department_id else None,
            "min_hours_late": min_hours,
            "max_hours_late": max_hours,
            "score": score,
        },
        None,
    )


@routes.get("/penalty-rules")
async def list_penalty_rules(request: web.Request) -> web.Response:
    """Global qoidalar + joriy modul bo'limlarining qoidalari, kechikish
    oralig'i bo'yicha tartiblangan."""
    async with async_session() as session:
        rules = await PenaltyRuleRepository(session).list_all()
        department_repo = DepartmentRepository(session)
        names = {}
        for rule in rules:
            if rule.department_id is not None and rule.department_id not in names:
                department = await department_repo.get_by_id(rule.department_id)
                names[rule.department_id] = department.name if department else None
        scope = await module_scope(request, session)

    rules = [r for r in rules if r.department_id is None or in_module(scope, r.department_id)]
    rules.sort(key=lambda r: (r.department_id is not None, r.department_id or 0, r.min_hours_late))
    return web.json_response([_penalty_rule_json(r, names.get(r.department_id)) for r in rules])


@routes.post("/penalty-rules")
async def create_penalty_rule(request: web.Request) -> web.Response:
    fields, error = _parse_penalty_rule_body(await request.json())
    if error:
        return err(error)
    if not _department_scope_ok(request, fields["department_id"]):
        return err("bu bo'lim sizning doirangizda emas", 403)

    async with async_session() as session:
        if fields["department_id"] is not None:
            if await DepartmentRepository(session).get_by_id(fields["department_id"]) is None:
                return err("bo'lim topilmadi", 404)
        rule = await PenaltyRuleRepository(session).create(**fields)
        await session.commit()

    return web.json_response(_penalty_rule_json(rule), status=201)


@routes.post("/penalty-rules/{rule_id}")
async def update_penalty_rule(request: web.Request) -> web.Response:
    rule_id = int(request.match_info["rule_id"])
    fields, error = _parse_penalty_rule_body(await request.json())
    if error:
        return err(error)

    async with async_session() as session:
        repo = PenaltyRuleRepository(session)
        rule = await repo.get_by_id(rule_id)
        if rule is None:
            return err("not_found", 404)
        # Eski VA yangi bo'lim — ikkalasi ham chaqiruvchi doirasida bo'lishi kerak.
        if not _department_scope_ok(request, rule.department_id) or not _department_scope_ok(
            request, fields["department_id"]
        ):
            return err("bu bo'lim sizning doirangizda emas", 403)
        if rule.department_id is None and not _global_top_rule_survives(
            await repo.list_all(),
            changed_id=rule_id,
            new_max_hours=fields["max_hours_late"],
            deleting=False,
        ):
            return err(
                "global jadvalda ochiq yuqori chegara (max bo'sh) qatori qolishi shart — "
                "aks holda juda kech tugagan vazifa umuman jarimasiz o'tib ketadi",
                409,
            )
        await repo.update(rule, **fields)
        await session.commit()

    return web.json_response(_penalty_rule_json(rule))


@routes.delete("/penalty-rules/{rule_id}")
async def delete_penalty_rule(request: web.Request) -> web.Response:
    rule_id = int(request.match_info["rule_id"])
    async with async_session() as session:
        repo = PenaltyRuleRepository(session)
        rule = await repo.get_by_id(rule_id)
        if rule is None:
            return err("not_found", 404)
        if not _department_scope_ok(request, rule.department_id):
            return err("bu bo'lim sizning doirangizda emas", 403)
        if rule.department_id is None and not _global_top_rule_survives(
            await repo.list_all(), changed_id=rule_id, new_max_hours=None, deleting=True
        ):
            return err(
                "global jadvalda ochiq yuqori chegara (max bo'sh) qatori qolishi shart — "
                "aks holda juda kech tugagan vazifa umuman jarimasiz o'tib ketadi",
                409,
            )
        await repo.delete(rule)
        await session.commit()

    return web.json_response({"deleted": True})


@routes.get("/reassign-candidates")
async def list_reassign_candidates(request: web.Request) -> web.Response:
    """8.3-band: "Ko'rib chiqish" bildirishnomasi endi Mini App ichidagi shu
    ro'yxat orqali ham ko'rinadi."""
    async with async_session() as session:
        tasks = await TaskRepository(session).list_awaiting_reassignment_review()
        department_repo = DepartmentRepository(session)
        scope = await module_scope(request, session)
        items = []
        for task in tasks:
            if not _department_scope_ok(request, task.current_department_id):
                continue
            if not in_module(scope, task.current_department_id):
                continue
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
        if not _department_scope_ok(request, task.current_department_id):
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
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None:
            return err("not_found", 404)
        if not _department_scope_ok(request, task.current_department_id):
            return err("not_found", 404)
        old_employee_ids = [
            a.employee_id for a in await TaskAssignmentRepository(session).list_by_task(task_id)
        ]

    try:
        await task_service.reassign_task_brigade(task_id, new_brigade_id, bot=request.config_dict["bot"])
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


@routes.get("/pending-claims")
async def list_pending_claims(request: web.Request) -> web.Response:
    """Mebel moduli: ishchilarning Pauza/Yakunlash so'rovlari, tasdiqlashni
    kutmoqda. Doirasi `claim_service.list_pending_claims_for_supervisor()`
    ichida hal qilinadi (ADMIN/bo'limsiz SUPERVISOR — hammasi, boshqa
    SUPERVISOR — faqat o'z bo'limi)."""
    employee = request["employee"]
    claims = await claim_service.list_pending_claims_for_supervisor(employee.id)

    async with async_session() as session:
        task_repo = TaskRepository(session)
        employee_repo = EmployeeRepository(session)
        department_repo = DepartmentRepository(session)
        scope = await module_scope(request, session)

        items = []
        for claim in claims:
            task = await task_repo.get_by_id(claim.task_id)
            if task is not None and not in_module(scope, task.current_department_id):
                continue
            claimant = await employee_repo.get_by_id(claim.employee_id)
            department = (
                await department_repo.get_by_id(task.current_department_id)
                if task is not None and task.current_department_id is not None
                else None
            )
            items.append(
                {
                    "id": claim.id,
                    "task_id": claim.task_id,
                    "task_title": task.title if task is not None else None,
                    "department": department.name if department else None,
                    "action_type": claim.action_type.value,
                    "claimed_at": claim.claimed_at.isoformat(),
                    "employee_name": claimant.full_name if claimant is not None else None,
                    "reason": claim.reason,
                }
            )
    return web.json_response(items)


@routes.post("/claims/{claim_id}/approve")
async def approve_claim(request: web.Request) -> web.Response:
    claim_id = int(request.match_info["claim_id"])
    employee = request["employee"]

    try:
        claim = await claim_service.approve_claim(claim_id, employee.id, bot=request.config_dict["bot"])
    except claim_service.ClaimNotFoundError:
        return err("not_found", 404)
    except claim_service.InvalidClaimStateError as exc:
        return err(str(exc), 409)
    except claim_service.NotAuthorizedToReviewError as exc:
        return err(str(exc), 403)

    try:
        await notification_service.notify_claim_approved(request.config_dict["bot"], claim.id)
    except Exception:
        logger.exception("notify_claim_approved xatosi (claim_id=%s)", claim.id)

    return web.json_response({"id": claim.id, "status": claim.status.value})


@routes.post("/claims/{claim_id}/reject")
async def reject_claim(request: web.Request) -> web.Response:
    claim_id = int(request.match_info["claim_id"])
    employee = request["employee"]
    body = await request.json()
    note = (body.get("note") or "").strip() or None

    try:
        claim = await claim_service.reject_claim(claim_id, employee.id, note=note)
    except claim_service.ClaimNotFoundError:
        return err("not_found", 404)
    except claim_service.InvalidClaimStateError as exc:
        return err(str(exc), 409)
    except claim_service.NotAuthorizedToReviewError as exc:
        return err(str(exc), 403)

    try:
        await notification_service.notify_claim_rejected(request.config_dict["bot"], claim.id)
    except Exception:
        logger.exception("notify_claim_rejected xatosi (claim_id=%s)", claim.id)

    return web.json_response({"id": claim.id, "status": claim.status.value})
