"""Profil ekrani: joriy xodim ma'lumoti + til tanlash (uz/ru)."""

from aiohttp import web

from core.database import async_session
from db.models.department import Department
from db.models.employee import Employee
from db.repositories import BrigadeRepository, DepartmentRepository
from miniapp.util import err
from services import employee_service
from utils.enums import Role
from utils.formatters import ROLE_LABELS
from utils.modules import MEBEL, NAZORAT_TRELLO

routes = web.RouteTableDef()


def _resolve_available_modules(employee: Employee, department: Department | None) -> list[str]:
    """Joriy xodim Mini App'da qaysi modul(lar)ni — "Fasad seh" (`MEBEL`)
    va/yoki "Nazorat Trello" (`NAZORAT_TRELLO`) — ko'ra olishini aniqlaydi.
    Modul tanlash ekranini ko'rsatish/o'tkazib yuborishni frontend shu
    ro'yxatga qarab hal qiladi (nomlar tuzog'i: `utils/modules.py`)."""
    if employee.role == Role.ADMIN:
        return [MEBEL, NAZORAT_TRELLO]
    if employee.role == Role.SUPERVISOR:
        if employee.department_id is None:
            return [MEBEL, NAZORAT_TRELLO]
        return [department.module] if department else [MEBEL]
    if employee.department_id is not None:
        return [department.module] if department else [MEBEL]
    return [MEBEL]


@routes.get("/me")
async def get_me(request: web.Request) -> web.Response:
    employee = request["employee"]

    department_name = None
    brigade_name = None
    department = None
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
            "available_modules": _resolve_available_modules(employee, department),
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
