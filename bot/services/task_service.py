"""Yangi vazifa yaratish va Trello bilan integratsiya (7.1-band).

`timer_service.py` mavjud vazifaning holatini boshqaradi; bu servis esa YANGI
vazifani Trello'da va bazada yaratadi. Tartib ataylab shunday: AVVAL Trello'da
karta ochiladi, FAQAT muvaffaqiyatli bo'lsagina bazaga yoziladi — aks holda
bazada Trello'siz "osilib qolgan" vazifa paydo bo'lardi. Aksincha tartib
(avval baza, keyin Trello) bazada Trello kartasiz vazifa qoldirib ketishi
mumkin edi, buni ataylab oldini oldik.
"""

from datetime import datetime, timezone

from config import settings
from core.database import async_session
from db.models.task import Task
from db.repositories import DepartmentRepository, EmployeeRepository, TaskAssignmentRepository, TaskRepository
from trello.client import TrelloClient
from utils.enums import TaskStatus, TaskType


class DepartmentNotFoundError(Exception):
    """Berilgan department_id topilmadi."""


class DepartmentNotConfiguredError(Exception):
    """Department uchun Trello ro'yxati (trello_list_id) sozlanmagan."""


class TaskNotFoundError(Exception):
    """Berilgan task_id bo'yicha vazifa topilmadi."""


class InvalidTaskStateError(Exception):
    """So'ralgan amal vazifaning joriy holatiga mos kelmaydi."""


async def create_task(
    title: str,
    description: str | None,
    deadline: datetime,
    department_id: int,
    employee_ids: list[int],
) -> Task:
    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(department_id)
        if department is None:
            raise DepartmentNotFoundError(f"Department {department_id} topilmadi")
        if not department.trello_list_id:
            raise DepartmentNotConfiguredError(
                f"'{department.name}' yo'nalishi uchun Trello ro'yxati (list) sozlanmagan"
            )
        list_id = department.trello_list_id

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        card = await trello.create_card(list_id=list_id, name=title, desc=description or "", due=deadline)

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.create(
            trello_card_id=card["id"],
            task_type=TaskType.ORDER,
            title=title,
            description=description,
            deadline=deadline,
            status=TaskStatus.ACTIVE,
            current_department_id=department_id,
            started_at=datetime.now(timezone.utc),
        )

        for employee_id in employee_ids:
            await assignment_repo.create(task_id=task.id, employee_id=employee_id)

        await session.commit()
        return task


async def advance_task_stage(completed_task_id: int) -> Task | None:
    """6.1/7.4-band: ko'p bosqichli buyurtma progressiyasi. Bosqich
    yakunlanganda (ishchining "Yakunlash" tugmasi orqali) chaqiriladi.

    Joriy bo'limning `next_department_id`si sozlanmagan bo'lsa (yoki bo'lim
    umuman yo'q) — buyurtma to'liq tugagan deb hisoblanadi, `None` qaytadi va
    hech narsa yaratilmaydi. Aks holda: Trello karta DARHOL keyingi bo'lim
    list'iga ko'chiriladi, so'ng yangi bosqich-qatori `PENDING_SETUP` holatida
    yaratiladi (`previous_task_id` orqali eskisiga zanjirlangan, muddat/xodim
    hali YO'Q — buni nazoratchi/admin `activate_pending_stage()` orqali
    kiritadi, C.2-band qarori: bosqich muddatini tizim o'zi to'qimaydi).

    MUHIM: bu funksiya `timer_service.finish_task()` ICHIDAN chaqirilMAYDI —
    faqat ishchining "Yakunlash" handler'i orqali. `daily_sync_job`ning Trello
    karta arxivlanganda avtomatik yopish yo'li buni chaqirmaydi: karta
    arxivlanishi butun buyurtmaning TERMINAL yopilishini bildiradi, keyingi
    bosqichga o'tish emas — ikkovi ziddiyatli bo'lardi."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        department_repo = DepartmentRepository(session)

        completed_task = await task_repo.get_by_id(completed_task_id)
        if completed_task is None:
            raise TaskNotFoundError(f"Task {completed_task_id} topilmadi")
        if completed_task.current_department_id is None:
            return None

        current_department = await department_repo.get_by_id(completed_task.current_department_id)
        if current_department is None or current_department.next_department_id is None:
            return None

        next_department = await department_repo.get_by_id(current_department.next_department_id)
        if next_department is None:
            return None
        if not next_department.trello_list_id:
            raise DepartmentNotConfiguredError(
                f"'{next_department.name}' yo'nalishi uchun Trello ro'yxati (list) sozlanmagan"
            )

        card_id = completed_task.trello_card_id
        next_department_id = next_department.id
        next_list_id = next_department.trello_list_id
        title = completed_task.title
        description = completed_task.description

    if card_id:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card_id, next_list_id)

    async with async_session() as session:
        task_repo = TaskRepository(session)
        next_task = await task_repo.create(
            trello_card_id=card_id,
            task_type=TaskType.ORDER,
            title=title,
            description=description,
            deadline=None,
            status=TaskStatus.PENDING_SETUP,
            current_department_id=next_department_id,
            started_at=datetime.now(timezone.utc),
            previous_task_id=completed_task_id,
        )
        await session.commit()
        return next_task


async def activate_pending_stage(task_id: int, *, deadline: datetime, employee_ids: list[int]) -> Task:
    """6.1/7.4-band: nazoratchi/admin `PENDING_SETUP` bosqichga muddat va
    xodim(lar)ni belgilagach chaqiriladi. Karta joyi allaqachon
    `advance_task_stage()`da ko'chirilgan — bu yerda faqat muddat/xodim
    yozilib, taymer (`status=ACTIVE`) boshlanadi."""
    if not employee_ids:
        raise ValueError("Kamida bitta xodim tanlanishi kerak")

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.status != TaskStatus.PENDING_SETUP:
            raise InvalidTaskStateError(
                f"Task {task_id} sozlashni kutmayapti (joriy holat: {task.status})"
            )

        await task_repo.update(task, deadline=deadline, status=TaskStatus.ACTIVE)
        for employee_id in employee_ids:
            await assignment_repo.create(task_id=task.id, employee_id=employee_id)

        await session.commit()
        return task


async def create_misc_task(*, text: str, deadline: datetime, employee_ids: list[int]) -> Task:
    """9-band: "Vazifalar" moduli — Trello'siz, faqat tizim ichida
    boshqariladigan alohida topshiriq (masalan "Ofisni tozalash"). Trello'ga
    HECH QANDAY murojaat qilinmaydi — faqat bazaga yoziladi. Bildirishnoma
    bu funksiya ichida YUBORILMAYDI (chaqiruvchi handler
    `notification_service.notify_task_started()` orqali o'zi yuboradi —
    `create_task()` bilan bir xil naqsh).

    TZ 9-band: "Bitta vazifaga 3 tagacha odam belgilanishi mumkin" — bu
    cheklov shu yerda tekshiriladi (UI validatsiyasiga tayanmaydi)."""
    if not employee_ids:
        raise ValueError("Kamida bitta xodim tanlanishi kerak")
    if len(employee_ids) > 3:
        raise ValueError("Bitta vazifaga ko'pi bilan 3 ta xodim biriktirish mumkin")

    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        # Tashkiliy kontekst uchun (statistika/jarima qoidalari bo'lim
        # bo'yicha bo'lishi mumkin) — birinchi xodimning bo'limidan olinadi,
        # aniq so'ralmaydi (TZning o'zida MISC yaratishda bo'lim tanlash
        # talab qilinmagan).
        first_employee = await employee_repo.get_by_id(employee_ids[0])
        department_id = first_employee.department_id if first_employee else None

        task = await task_repo.create(
            trello_card_id=None,
            task_type=TaskType.MISC,
            title=text[:255],
            description=text,
            deadline=deadline,
            status=TaskStatus.ACTIVE,
            current_department_id=department_id,
            started_at=datetime.now(timezone.utc),
        )

        for employee_id in employee_ids:
            await assignment_repo.create(task_id=task.id, employee_id=employee_id)

        await session.commit()
        return task
