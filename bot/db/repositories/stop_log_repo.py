from sqlalchemy import select

from db.models.stop_log import StopLog
from db.repositories.base import BaseRepository


class StopLogRepository(BaseRepository[StopLog]):
    model = StopLog

    async def get_active_stop(self, task_id: int) -> StopLog | None:
        """Vazifada hozir davom etayotgan (hali resumed_at qo'yilmagan) Stop bormi (7.5-band)."""
        result = await self.session.execute(
            select(StopLog).where(
                StopLog.task_id == task_id, StopLog.resumed_at.is_(None)
            )
        )
        return result.scalar_one_or_none()
