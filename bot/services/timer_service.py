"""Vazifa holati va "Stop" oqimini boshqaradi (7.4, 7.5-band).

Har bir funksiya o'z sessiyasini ochib-yopadi va oxirida commit qiladi (Unit of Work):
handler/job'lar bevosita repository yoki sessiya bilan ishlamaydi, faqat shu
funksiyalarni chaqiradi. `core/database.py`dagi `async_session` `expire_on_commit=False`
bilan sozlangani uchun qaytarilgan ORM obyektlari commit'dan keyin ham xavfsiz o'qiladi.
"""

from datetime import datetime, timezone

from core.database import async_session
from db.models.stop_log import StopLog
from db.models.task import Task
from db.repositories import StopLogRepository, TaskAssignmentRepository, TaskRepository
from utils.enums import TaskStatus


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
