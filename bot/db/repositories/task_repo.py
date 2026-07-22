from datetime import datetime, timedelta

from sqlalchemy import select

from db.models.department import Department
from db.models.task import Task
from db.repositories.base import BaseRepository
from utils.enums import TaskStatus, TaskType

_OPEN_STATUSES = [TaskStatus.ACTIVE, TaskStatus.STOPPED]


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

    async def list_deadline_approaching(self, *, now: datetime, within_hours: int = 24) -> list[Task]:
        """7.2-band: "1 kun qoldi" — hali signal yuborilmagan (`day_left_notified_at
        IS NULL`), muddati [now, now+within_hours) oralig'ida bo'lgan faol/
        to'xtatilgan vazifalar (`overdue_watch_job`, soatiga bir marta)."""
        threshold = now + timedelta(hours=within_hours)
        result = await self.session.execute(
            select(Task).where(
                Task.status.in_(_OPEN_STATUSES),
                Task.deadline.isnot(None),
                Task.deadline > now,
                Task.deadline <= threshold,
                Task.day_left_notified_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_newly_overdue(self, *, now: datetime) -> list[Task]:
        """7.2-band: muddati o'tib ketgan, lekin hali `OVERDUE` deb
        belgilanmagan faol/to'xtatilgan vazifalar."""
        result = await self.session.execute(
            select(Task).where(
                Task.status.in_(_OPEN_STATUSES),
                Task.deadline.isnot(None),
                Task.deadline < now,
            )
        )
        return list(result.scalars().all())

    async def list_overdue_for_reassignment_check(
        self, *, now: datetime, hours_overdue: int = 48
    ) -> list[Task]:
        """8.3-band: bo'limi `auto_reassign_after_48h=True` bo'lgan, muddatidan
        `hours_overdue` soatdan ortiq o'tgan, hali signal berilmagan OVERDUE
        vazifalar."""
        threshold = now - timedelta(hours=hours_overdue)
        result = await self.session.execute(
            select(Task)
            .join(Department, Task.current_department_id == Department.id)
            .where(
                Task.status == TaskStatus.OVERDUE,
                Department.auto_reassign_after_48h.is_(True),
                Task.deadline < threshold,
                Task.reassignment_signaled_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_awaiting_reassignment_review(self) -> list[Task]:
        """8.3-band admin UI (Mini App): signal allaqachon berilgan
        (`reassignment_signaled_at`), hali OVERDUE va hali qo'lda ko'rib
        chiqilmagan (`reassigned_at IS NULL`) buyurtmalar ro'yxati."""
        result = await self.session.execute(
            select(Task).where(
                Task.status == TaskStatus.OVERDUE,
                Task.reassignment_signaled_at.isnot(None),
                Task.reassigned_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_long_running_stages(self, *, threshold_days: int, now: datetime) -> list[Task]:
        """8.6-band 1-qoida: hozirgi bosqichda (`started_at`dan hisoblab)
        `threshold_days`dan ORTIQ (qat'iy >) turib qolgan, hali yakunlanmagan
        ORDER vazifalar (`overdue_watch_job`, soatiga bir marta). MISC
        vazifalarda (9-band) bo'lim zanjiri umuman yo'q, shu sabab chetlab
        o'tiladi."""
        threshold = now - timedelta(days=threshold_days)
        result = await self.session.execute(
            select(Task).where(
                Task.task_type == TaskType.ORDER,
                Task.status.in_(_OPEN_STATUSES + [TaskStatus.OVERDUE]),
                Task.started_at < threshold,
            )
        )
        return list(result.scalars().all())
