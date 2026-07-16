from datetime import datetime

from sqlalchemy import select

from db.models.task import Task
from db.repositories.base import BaseRepository
from utils.enums import TaskStatus


class TaskRepository(BaseRepository[Task]):
    model = Task

    async def get_by_trello_card_id(self, trello_card_id: str) -> Task | None:
        """Trello webhook/sinxronizatsiya kartani karta ID orqali topadi (6.3, 7.1-band).

        Ko'p bosqichli buyurtmada (6.1/7.4-band) bir nechta bosqich-qatori BIR
        XIL kartaga ishora qilishi mumkin (`task.py`dagi izohga qarang) — shu
        sabab faqat hali YAKUNLANMAGAN (joriy) qatorni qaytaramiz. Bir nechta
        mos qator bo'lsa ham (masalan ikkalasi ham COMPLETED emas holati
        bo'lishi mumkin emas, lekin himoya sifatida) eng oxirgisini olamiz."""
        result = await self.session.execute(
            select(Task)
            .where(Task.trello_card_id == trello_card_id, Task.status != TaskStatus.COMPLETED)
            .order_by(Task.id.desc())
        )
        return result.scalars().first()

    async def list_by_status(self, status: TaskStatus) -> list[Task]:
        """Kunlik label sinxronizatsiyasi va taymer job'lari uchun (6.3, 7.4-band)."""
        result = await self.session.execute(select(Task).where(Task.status == status))
        return list(result.scalars().all())

    async def list_due_between(
        self, since: datetime, until: datetime, statuses: list[TaskStatus]
    ) -> list[Task]:
        """[since, until) oralig'ida muddati tugaydigan, berilgan status(lar)dagi
        vazifalar — kunlik eslatma job'i uchun (7.3-band)."""
        result = await self.session.execute(
            select(Task).where(
                Task.deadline >= since,
                Task.deadline < until,
                Task.status.in_(statuses),
            )
        )
        return list(result.scalars().all())
