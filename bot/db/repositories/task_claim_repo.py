from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.models.task_claim import TaskClaim
from db.repositories.base import BaseRepository
from utils.enums import ClaimStatus


class TaskClaimRepository(BaseRepository[TaskClaim]):
    model = TaskClaim

    async def get_pending_for_task(self, task_id: int) -> TaskClaim | None:
        """Bir vaqtda faqat bitta PENDING so'rov bo'lishi kerak — yangi so'rov
        yaratishdan oldin shu tekshiriladi (`services/claim_service.py`)."""
        result = await self.session.execute(
            select(TaskClaim).where(TaskClaim.task_id == task_id, TaskClaim.status == ClaimStatus.PENDING)
        )
        return result.scalar_one_or_none()

    async def list_pending(self) -> list[TaskClaim]:
        """Rahbar/admin ko'rish ro'yxati uchun barcha PENDING so'rovlar —
        chaqiruvchi (`claim_service.list_pending_claims_for_supervisor`)
        bo'lim doirasiga qarab keyin filtrlaydi."""
        result = await self.session.execute(select(TaskClaim).where(TaskClaim.status == ClaimStatus.PENDING))
        return list(result.scalars().all())

    async def list_stale_pending(self, *, older_than_hours: int) -> list[TaskClaim]:
        """`overdue_watch_job`ning eskalatsiya bosqichi uchun: `claimed_at`dan
        berilgan soatdan ko'p vaqt o'tgan, hali PENDING so'rovlar."""
        threshold = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        result = await self.session.execute(
            select(TaskClaim).where(TaskClaim.status == ClaimStatus.PENDING, TaskClaim.claimed_at <= threshold)
        )
        return list(result.scalars().all())
