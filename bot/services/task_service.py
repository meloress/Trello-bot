"""Yangi vazifa yaratish va Trello bilan integratsiya (7.1-band).

`timer_service.py` mavjud vazifaning holatini boshqaradi; bu servis esa YANGI
vazifani Trello'da va bazada yaratadi. Tartib ataylab shunday: AVVAL Trello'da
karta ochiladi, FAQAT muvaffaqiyatli bo'lsagina bazaga yoziladi — aks holda
bazada Trello'siz "osilib qolgan" vazifa paydo bo'lardi. Aksincha tartib
(avval baza, keyin Trello) bazada Trello kartasiz vazifa qoldirib ketishi
mumkin edi, buni ataylab oldini oldik.

6.2-band (karta a'zo + checklist): bular ASOSIY vazifa yaratish/o'tkazish
oqimidan KEYIN, ikkinchi-darajali effekt sifatida bajariladi — xato bo'lsa
faqat log qilinadi, asosiy oqim (karta/baza yozuvi) allaqachon muvaffaqiyatli
bo'lgani uchun foydalanuvchiga soxta xatolik ko'rsatilmaydi.
"""

import logging
from datetime import datetime, timezone

from config import settings
from core.database import async_session
from db.models.task import Task
from db.repositories import (
    DepartmentRepository,
    EmployeeRepository,
    TaskAssignmentRepository,
    TaskRepository,
)
from services import penalty_service
from trello.client import TrelloClient
from utils.enums import TaskStatus, TaskType

logger = logging.getLogger(__name__)


class DepartmentNotFoundError(Exception):
    """Berilgan department_id topilmadi."""


class DepartmentNotConfiguredError(Exception):
    """Department uchun Trello ro'yxati (trello_list_id) sozlanmagan."""


class TaskNotFoundError(Exception):
    """Berilgan task_id bo'yicha vazifa topilmadi."""


class InvalidTaskStateError(Exception):
    """So'ralgan amal vazifaning joriy holatiga mos kelmaydi."""


async def _collect_department_chain_names(department_repo: DepartmentRepository, start_department_id: int) -> list[str]:
    """6.2-band: checklist punktlari uchun — `start_department_id`dan
    boshlab `next_department_id` zanjiri bo'ylab bo'lim nomlari ro'yxati."""
    names: list[str] = []
    current_id: int | None = start_department_id
    while current_id is not None:
        department = await department_repo.get_by_id(current_id)
        if department is None:
            break
        names.append(department.name)
        current_id = department.next_department_id
    return names


async def _add_members_to_card(card_id: str, employee_ids: list[int]) -> None:
    """6.2-band: karta a'zolari. `trello_member_id` yo'q xodim — faqat
    log (ikkinchi-darajali, asosiy oqimni to'xtatmaydi)."""
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        employees = [await employee_repo.get_by_id(eid) for eid in employee_ids]

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for employee in employees:
            if employee is None:
                continue
            if not employee.trello_member_id:
                logger.warning(
                    "Xodim '%s' (id=%s) uchun trello_member_id yo'q — kartaga a'zo sifatida qo'shilmadi",
                    employee.full_name, employee.id,
                )
                continue
            try:
                await trello.add_member_to_card(card_id, employee.trello_member_id)
            except Exception:
                logger.exception(
                    "Xodim '%s' (id=%s) kartaga (%s) a'zo sifatida qo'shilmadi", employee.full_name, employee.id, card_id
                )


async def _remove_members_from_card(card_id: str, employee_ids: list[int]) -> None:
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        employees = [await employee_repo.get_by_id(eid) for eid in employee_ids]

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for employee in employees:
            if employee is None or not employee.trello_member_id:
                continue
            try:
                await trello.remove_member_from_card(card_id, employee.trello_member_id)
            except Exception:
                logger.exception(
                    "Xodim '%s' (id=%s) kartadan (%s) a'zolikdan chiqarilmadi", employee.full_name, employee.id, card_id
                )


async def _create_stage_checklist(task_id: int, card_id: str, department_id: int) -> None:
    """6.2-band: bo'lim zanjiri bo'yicha checklist — har bosqich (departament)
    uchun bitta punkt. `task.trello_checklist_id`ga yoziladi."""
    async with async_session() as session:
        chain_names = await _collect_department_chain_names(DepartmentRepository(session), department_id)

    try:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            checklist = await trello.create_checklist(card_id, "Bosqichlar")
            for name in chain_names:
                await trello.add_checklist_item(checklist["id"], name)
    except Exception:
        logger.exception("Task %s uchun checklist yaratilmadi (karta %s)", task_id, card_id)
        return

    async with async_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        if task is not None:
            await task_repo.update(task, trello_checklist_id=checklist["id"])
            await session.commit()


async def create_task(
    title: str,
    description: str | None,
    deadline: datetime,
    department_id: int,
    employee_ids: list[int],
    client_id: int | None = None,
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
            client_id=client_id,
        )

        for employee_id in employee_ids:
            await assignment_repo.create(task_id=task.id, employee_id=employee_id)

        await session.commit()

    try:
        await _add_members_to_card(card["id"], employee_ids)
    except Exception:
        logger.exception("Task %s uchun karta a'zolari qo'shilmadi", task.id)

    await _create_stage_checklist(task.id, card["id"], department_id)

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

    6.2-band: eski bosqich checklist punkti "complete" deb belgilanadi, eski
    bosqich xodimlari kartadan a'zolikdan chiqariladi (yangi bosqich xodimlari
    hali tayinlanmagan — ular `activate_pending_stage()`da qo'shiladi).

    MUHIM: bu funksiya `timer_service.finish_task()` ICHIDAN chaqirilMAYDI —
    faqat ishchining "Yakunlash" handler'i orqali. `daily_sync_job`ning Trello
    karta arxivlanganda avtomatik yopish yo'li buni chaqirmaydi: karta
    arxivlanishi butun buyurtmaning TERMINAL yopilishini bildiradi, keyingi
    bosqichga o'tish emas — ikkovi ziddiyatli bo'lardi."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        department_repo = DepartmentRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

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
        checklist_id = completed_task.trello_checklist_id
        next_department_id = next_department.id
        next_list_id = next_department.trello_list_id
        current_department_name = current_department.name
        title = completed_task.title
        description = completed_task.description
        client_id = completed_task.client_id
        old_employee_ids = [a.employee_id for a in await assignment_repo.list_by_task(completed_task_id)]

    if card_id:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card_id, next_list_id)

            if checklist_id:
                try:
                    await trello.check_checklist_item_by_name(card_id, checklist_id, current_department_name)
                except Exception:
                    logger.exception(
                        "Task %s: checklist punkti '%s' belgilanmadi", completed_task_id, current_department_name
                    )

        if old_employee_ids:
            try:
                await _remove_members_from_card(card_id, old_employee_ids)
            except Exception:
                logger.exception("Task %s: eski bosqich xodimlari kartadan olib tashlanmadi", completed_task_id)

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
            trello_checklist_id=checklist_id,
            client_id=client_id,
        )
        await session.commit()
        return next_task


async def activate_pending_stage(task_id: int, *, deadline: datetime, employee_ids: list[int]) -> Task:
    """6.1/7.4-band: nazoratchi/admin `PENDING_SETUP` bosqichga muddat va
    xodim(lar)ni belgilagach chaqiriladi. Karta joyi allaqachon
    `advance_task_stage()`da ko'chirilgan — bu yerda faqat muddat/xodim
    yozilib, taymer (`status=ACTIVE`) boshlanadi. 6.2-band: yangi bosqich
    xodimlari kartaga a'zo sifatida qo'shiladi (bu funksiyaga birinchi
    Trello a'zo chaqiruvi — eski bosqichda bu ish `advance_task_stage()`da
    bajarilgan)."""
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
        card_id = task.trello_card_id

    if card_id:
        try:
            await _add_members_to_card(card_id, employee_ids)
        except Exception:
            logger.exception("Task %s: yangi bosqich xodimlari kartaga qo'shilmadi", task_id)

    return task


async def reassign_task_brigade(task_id: int, new_brigade_id: int) -> Task:
    """8.3-band: uzoq kechikkan (OVERDUE, avtomatik aniqlangan —
    `overdue_watch_job._process_reassignment_signals`) buyurtmani boshqa
    brigadaga QO'LDA o'tkazish (yakuniy tasdiq rahbarda,
    `handlers/admin/reassign_task.py`). Ikkiga bo'lingan jarima mantig'i
    (foydalanuvchi tasdiqlagan qaror): eski brigadaga DARHOL to'liq jarima
    (hozirgi vaqtga nisbatan kechikish), yangi brigada uchun hisoblash
    bazasi shu o'tkazish vaqtidan boshlanadi (`task.reassigned_at` —
    `calculate_and_apply_task_penalty()` shunga qarab `deadline` o'rniga
    shu vaqtdan hisoblaydi). Task `COMPLETED` qilinmaydi — taymer davom etadi."""
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)
        employee_repo = EmployeeRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.status != TaskStatus.OVERDUE:
            raise InvalidTaskStateError(
                f"Task {task_id} OVERDUE emas, brigadaga o'tkazib bo'lmaydi (joriy holat: {task.status})"
            )

        new_employees = await employee_repo.list_by_brigade(new_brigade_id)
        new_employee_ids = [e.id for e in new_employees]
        if not new_employee_ids:
            raise ValueError(f"Brigada {new_brigade_id}da faol xodim yo'q")

        old_employee_ids = [a.employee_id for a in await assignment_repo.list_by_task(task_id)]
        department_id = task.current_department_id
        deadline = task.deadline
        card_id = task.trello_card_id

    hours_late = int((now - deadline).total_seconds() // 3600)
    await penalty_service.apply_penalty_for_employees(
        task_id=task_id,
        department_id=department_id,
        employee_ids=old_employee_ids,
        hours_late=hours_late,
        reason_label="Brigadaga o'tkazish (eski brigada, darhol jarima)",
    )

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        for assignment in await assignment_repo.list_by_task(task_id):
            await assignment_repo.delete(assignment)
        for employee_id in new_employee_ids:
            await assignment_repo.create(task_id=task_id, employee_id=employee_id)

        await task_repo.update(task, reassigned_at=now)
        await session.commit()

    if card_id:
        try:
            await _remove_members_from_card(card_id, old_employee_ids)
        except Exception:
            logger.exception("Task %s: eski brigada a'zolari kartadan olib tashlanmadi", task_id)
        try:
            await _add_members_to_card(card_id, new_employee_ids)
        except Exception:
            logger.exception("Task %s: yangi brigada a'zolari kartaga qo'shilmadi", task_id)

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
        # bo'yicha bo'lishi mumkin) — birinchi tanlangan xodimning bo'limidan
        # olinadi, aniq so'ralmaydi (TZning o'zida MISC yaratishda bo'lim
        # tanlash talab qilinmagan).
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
