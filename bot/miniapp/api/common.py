"""Profil ekrani: joriy xodim ma'lumoti + til tanlash (uz/ru)."""

from aiohttp import web

from core.database import async_session
from db.repositories import BrigadeRepository, DepartmentRepository
from keyboards.admin_kb import ROLE_LABELS
from miniapp.util import err
from services import employee_service

routes = web.RouteTableDef()


@routes.get("/me")
async def get_me(request: web.Request) -> web.Response:
    employee = request["employee"]

    department_name = None
    brigade_name = None
    async with async_session() as session:
        if employee.department_id is not None:
            department = await DepartmentRepository(session).get_by_id(employee.department_id)
            department_name = department.name if department else None
        if employee.brigade_id is not None:
            brigade = await BrigadeRepository(session).get_by_id(employee.brigade_id)
            brigade_name = brigade.name if brigade else None

    return web.json_response(
        {
            "id": employee.id,
            "full_name": employee.full_name,
            "role": employee.role.value,
            "role_label": ROLE_LABELS.get(employee.role, employee.role.value),
            "phone_number": employee.phone_number,
            "department": department_name,
            "brigade": brigade_name,
            "language": employee.language,
        }
    )


@routes.post("/me/language")
async def set_language(request: web.Request) -> web.Response:
    employee = request["employee"]
    body = await request.json()
    language = body.get("language")
    if language not in ("uz", "ru"):
        return err("invalid_language")

    await employee_service.update_employee(employee.id, language=language)
    return web.json_response({"language": language})
