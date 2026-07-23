"""Vazifa holati va "Stop" oqimini boshqaradi (7.4, 7.5-band).

Har bir funksiya o'z sessiyasini ochib-yopadi va oxirida commit qiladi (Unit of Work):
handler/job'lar bevosita repository yoki sessiya bilan ishlamaydi, faqat shu
funksiyalarni chaqiradi. `core/database.py`dagi `async_session` `expire_on_commit=False`
bilan sozlangani uchun qaytarilgan ORM obyektlari commit'dan keyin ham xavfsiz o'qiladi.
"""

import logging
from datetime import datetime, timezone

from config import settings
from core.database import async_session
from db.models.stop_log import StopLog
from db.models.task import Task
from db.repositories import DepartmentRepository, StopLogRepository, TaskAssignmentRepository, TaskRepository
from trello.client import TrelloClient
from utils.enums import TaskStatus

logger = logging.getLogger(__name__)


class TaskNotFoundError(Exception):
    """Berilgan task_id bo'yicha vazifa topilmadi."""


class InvalidTaskStateError(Exception):
    """So'ralgan amal vazifaning joriy holatiga mos kelmaydi."""


async def start_task(task_id: int, employee_ids: list[int]) -> Task:
    """Vazifani faollashtiradi, xodimlarni biriktiradi. Allaqachon biriktirilgan
    xodimlar qayta yozilmaydi (UNIQUE(task_id, employee_id))."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.status == TaskStatus.COMPLETED:
            raise InvalidTaskStateError(f"Task {task_id} allaqachon yakunlangan, qayta boshlab bo'lmaydi")

        already_assigned = {a.employee_id for a in await assignment_repo.list_by_task(task_id)}
        for employee_id in employee_ids:
            if employee_id not in already_assigned:
                await assignment_repo.create(task_id=task.id, employee_id=employee_id)

        await task_repo.update(task, status=TaskStatus.ACTIVE, started_at=datetime.now(timezone.utc))

        await session.commit()
        return task


async def _move_card_to_stop_list(card_id: str, department_id: int) -> None:
    """Fasad sex TZ (Phase 5): bo'lim `stop_target_list_id` sozlagan bo'lsa,
    "Stop" bosilganda karta shu maxsus Trello ro'yxatiga ko'chiriladi
    (mavjud label o'zgarishi bilan bir qatorda, ikkinchi-darajali effekt —
    `task_service.py`dagi `_create_stage_checklist` bilan bir xil
    try/except-log-only naqsh). `stop_target_list_id=None` bo'lgan bo'limlar
    uchun (mavjud mebel liniyasidagi HAMMA bo'lim) bu funksiya HECH QANDAY
    Trello chaqiruvi qilmaydi — bugungi xatti-harakat o'zgarishsiz qoladi."""
    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(department_id)
    if department is None or not department.stop_target_list_id:
        return
    try:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card_id, department.stop_target_list_id)
    except Exception:
        logger.exception(
            "Task kartasi (%s) 'stopda' ro'yxatiga ko'chirilmadi (department=%s)", card_id, department_id
        )


async def _move_card_back_from_stop_list(card_id: str, department_id: int) -> None:
    """Yuqoridagisining teskarisi: "Resume" bosilganda karta bo'limning
    ODATIY ro'yxatiga (`trello_list_id`, YANGI `stop_target_list_id` ustuni
    emas) qaytariladi — FAQAT shu bo'lim `stop_target_list_id` sozlagan
    bo'lsa (aks holda karta hech qachon ko'chmagan, qaytarishning hojati
    yo'q)."""
    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(department_id)
    if department is None or not department.stop_target_list_id or not department.trello_list_id:
        return
    try:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card_id, department.trello_list_id)
    except Exception:
        logger.exception(
            "Task kartasi (%s) asosiy ro'yxatga qaytarilmadi (department=%s)", card_id, department_id
        )


async def stop_task(task_id: int, employee_id: int, reason: str) -> StopLog:
    """"Stop" tugmasi: faqat faol vazifani to'xtatadi, sabab yozish majburiy (7.5-band)."""
    if not reason or not reason.strip():
        raise ValueError("Sabab (reason) bo'sh bo'lishi mumkin emas")

    async with async_session() as session:
        task_repo = TaskRepository(session)
        stop_repo = StopLogRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.status != TaskStatus.ACTIVE:
            raise InvalidTaskStateError(
                f"Task {task_id} faol emas, to'xtatib bo'lmaydi (joriy holat: {task.status})"
            )
        assigned_ids = {a.employee_id for a in await assignment_repo.list_by_task(task_id)}
        if employee_id not in assigned_ids:
            raise InvalidTaskStateError(f"Xodim {employee_id} bu vazifaga tayinlanmagan")

        await task_repo.update(task, status=TaskStatus.STOPPED)
        stop_log = await stop_repo.create(
            task_id=task.id,
            employee_id=employee_id,
            reason=reason,
            stopped_at=datetime.now(timezone.utc),
        )

        await session.commit()
        card_id = task.trello_card_id
        department_id = task.current_department_id

    # Fasad sex TZ (Phase 5): DB holati (STOPPED + StopLog) allaqachon
    # commit qilingan — bu Trello karta ko'chirishi ikkinchi-darajali effekt,
    # muvaffaqiyatsiz bo'lsa ham Stop amali o'zi muvaffaqiyatli hisoblanadi.
    if card_id and department_id is not None:
        await _move_card_to_stop_list(card_id, department_id)

    return stop_log


async def resume_task(task_id: int, employee_id: int | None = None) -> Task:
    """To'xtatilgan vazifani davom ettiradi: oxirgi faol stop_log'ni yopadi.
    `employee_id` berilsa (Mini App'dan chaqirilganda shunday) — faqat shu
    vazifaga tayinlangan xodim davom ettira oladi (zaxira tekshiruv, asosiy
    tekshiruv `miniapp/api/worker.py`'dagi `_is_assigned`). `None` bo'lsa
    (avtomatik job/skript chaqiruvi) tekshiruv o'tkazib yuboriladi."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        stop_repo = StopLogRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.status != TaskStatus.STOPPED:
            raise InvalidTaskStateError(
                f"Task {task_id} to'xtatilmagan, davom ettirib bo'lmaydi (joriy holat: {task.status})"
            )
        if employee_id is not None:
            assigned_ids = {a.employee_id for a in await assignment_repo.list_by_task(task_id)}
            if employee_id not in assigned_ids:
                raise InvalidTaskStateError(f"Xodim {employee_id} bu vazifaga tayinlanmagan")

        active_stop = await stop_repo.get_active_stop(task_id)
        if active_stop is None:
            raise InvalidTaskStateError(f"Task {task_id} uchun faol stop_log topilmadi")

        await stop_repo.update(active_stop, resumed_at=datetime.now(timezone.utc))
        await task_repo.update(task, status=TaskStatus.ACTIVE)

        await session.commit()
        card_id = task.trello_card_id
        department_id = task.current_department_id

    # Fasad sex TZ (Phase 5): xuddi stop_task() dagidek — DB holati allaqachon
    # commit qilingan, karta ko'chirishi ikkinchi-darajali effekt.
    if card_id and department_id is not None:
        await _move_card_back_from_stop_list(card_id, department_id)

    return task


async def finish_task(task_id: int, employee_id: int | None = None) -> Task:
    """Vazifani yakunlaydi va finished_at'ni belgilaydi. `employee_id` berilsa
    (Mini App'dan chaqirilganda shunday) — faqat shu vazifaga tayinlangan
    xodim yakunlashi mumkin (zaxira tekshiruv). `None` bo'lsa (masalan
    `jobs/daily_sync_job.py`'ning Trello-arxiv orqali avtomatik yopilishi —
    bunda aniq bitta "amal qilayotgan xodim" tushunchasi yo'q) tekshiruv
    o'tkazib yuboriladi."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.status == TaskStatus.COMPLETED:
            raise InvalidTaskStateError(f"Task {task_id} allaqachon yakunlangan")
        if employee_id is not None:
            assigned_ids = {a.employee_id for a in await assignment_repo.list_by_task(task_id)}
            if employee_id not in assigned_ids:
                raise InvalidTaskStateError(f"Xodim {employee_id} bu vazifaga tayinlanmagan")

        await task_repo.update(task, status=TaskStatus.COMPLETED, finished_at=datetime.now(timezone.utc))

        await session.commit()
        return task
