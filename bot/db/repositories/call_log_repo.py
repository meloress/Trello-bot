from sqlalchemy import select

from db.models.call_log import CallLog
from db.repositories.base import BaseRepository


class CallLogRepository(BaseRepository[CallLog]):
    model = CallLog

    async def list_by_lead(self, lead_id: int) -> list[CallLog]:
        result = await self.session.execute(
            select(CallLog).where(CallLog.lead_id == lead_id).order_by(CallLog.called_at.desc())
        )
        return list(result.scalars().all())
