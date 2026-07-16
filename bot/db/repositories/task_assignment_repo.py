from sqlalchemy import select

from db.models.task_assignment import TaskAssignment
from db.repositories.base import BaseRepository


class TaskAssignmentRepository(BaseRepository[TaskAssignment]):
    model = TaskAssignment

    async def list_by_task(self, task_id: int) -> list[TaskAssignment]:
        """Kartaga BELGILANGAN odamlarni topish — signal shularga boradi (3-band)."""
        result = await self.session.execute(
            select(TaskAssignment).where(TaskAssignment.task_id == task_id)
        )
        return list(result.scalars().all())

    async def list_by_employee(self, employee_id: int) -> list[TaskAssignment]:
        """Xodimning o'ziga tegishli vazifalari ro'yxati (11-band: kunlik ro'yxat)."""
        result = await self.session.execute(
            select(TaskAssignment).where(TaskAssignment.employee_id == employee_id)
        )
        return list(result.scalars().all())
