from aiohttp import web

from core.database import async_session
from db.repositories import DepartmentRepository, TaskRepository


def err(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


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
    return department is not None and department.module == "mebel"
