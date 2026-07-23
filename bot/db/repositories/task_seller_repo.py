from sqlalchemy import select

from db.models.task_seller import TaskSeller
from db.repositories.base import BaseRepository


class TaskSellerRepository(BaseRepository[TaskSeller]):
    model = TaskSeller

    async def list_by_task(self, task_id: int) -> list[TaskSeller]:
        """Buyurtmaga biriktirilgan sotuvchilar — Stop bildirishnomasi shularga
        ham boradi (notification_service.notify_task_stopped)."""
        result = await self.session.execute(
            select(TaskSeller).where(TaskSeller.task_id == task_id)
        )
        return list(result.scalars().all())
