from aiohttp import web

from core.database import async_session
from db.repositories import DepartmentRepository, TaskRepository
from utils.enums import Role
from utils.modules import MEBEL


def err(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def current_module(request: web.Request) -> str | None:
    """Mini App joriy modulini (`X-Module` sarlavhasi) qaytaradi, yoki `None`
    — sarlavha yuborilmagan bo'lsa (filtrsiz)."""
    return request.headers.get("X-Module") or None


async def module_scope(request: web.Request, session) -> set[int] | None:
    """Mini App QAYSI modulda ochilgan bo'lsa (`X-Module` sarlavhasi, frontend
    `nav.module`dan yuboradi) — o'sha modulning bo'lim id'lari. Sarlavha
    bo'lmasa `None` = filtr yo'q (eski/tashqi chaqiruvchilar buzilmaydi).

    Ikkala modul ("mebel"/"Fasad seh" va "fasad_sex"/"Nazorat Trello") bitta
    bazani baham ko'radi, lekin ular ALOHIDA korxona: xodimi ham, buyurtmasi
    ham, statistikasi ham aralashmasligi kerak. Modul chegarasi doim
    `Department.module` orqali o'tadi — shuning uchun filtr bo'lim id'lari
    to'plami ko'rinishida."""
    module = current_module(request)
    if not module:
        return None
    return {d.id for d in await DepartmentRepository(session).list_all() if d.module == module}


def in_module(scope: set[int] | None, department_id: int | None) -> bool:
    """Bo'limi YO'Q yozuv (masalan bo'lim biriktirilmagan admin/nazoratchi)
    hech qaysi modulga tegishli emas — shu sabab ikkalasida ham ko'rinadi,
    `_department_scope_ok`dagi "bo'limsiz SUPERVISOR — cheklovsiz" qoidasi
    bilan bir xil."""
    return scope is None or department_id is None or department_id in scope


def employee_in_module(scope: set[int] | None, module: str | None, employee) -> bool:
    """`in_module` ustiga bitta istisno: bo'limsiz NAZORATCHI faqat
    "Fasad seh"da ko'rinadi.

    Umumiy qoida (`in_module`) bo'limi yo'q yozuvni "hech qaysi modulga
    tegishli emas" deb hisoblab, IKKALASIDA ham ko'rsatadi. ADMIN uchun bu
    to'g'ri — u haqiqatan ikkala modulni boshqaradi. SUPERVISOR uchun esa
    noto'g'ri: nazoratchi — sexning nachalnigi (TZ 2-band), va
    `miniapp/api/common._resolve_available_modules()` unga allaqachon faqat
    "Fasad seh"ni beradi. Ro'yxatlarda esa u Nazorat Trelloda ham chiqib
    turardi — ya'ni bitta odam ikki xil joyda ikki xil ma'noda ko'rinardi.

    Nazorat Trelloga o'z nazoratchisi kerak bo'lganda — unga o'sha modulning
    BO'LIMI biriktiriladi, shunda bu tarmoq umuman ishlamaydi va u faqat
    o'z modulida ko'rinadi."""
    if employee.department_id is None and employee.role == Role.SUPERVISOR:
        return module is None or module == MEBEL
    return in_module(scope, employee.department_id)


async def is_mebel_task(task_id: int) -> bool:
    """Mebel moduli: Pauza/Yakunlash to'g'ridan-to'g'ri ishlamaydi — bu
    tekshiruv worker.py/brigadier.py'dagi shu amallarni himoya qiladi
    (haqiqiy amal faqat claim-tasdiqlash oqimi orqali). Department topilmasa
    (yoki task hali department'ga bog'lanmagan bo'lsa) bloklanmaydi."""
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
        if task is None or task.current_department_id is None:
            return False
        department = await DepartmentRepository(session).get_by_id(task.current_department_id)
    return department is not None and department.module == MEBEL
