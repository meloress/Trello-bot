from datetime import datetime

from sqlalchemy import select

from db.models.lead import Lead
from db.repositories.base import BaseRepository
from utils.enums import LeadStage

_CLOSED_STAGES = (LeadStage.CLOSED_WON, LeadStage.CLOSED_LOST)


class LeadRepository(BaseRepository[Lead]):
    model = Lead

    async def list_by_seller(self, employee_id: int, *, open_only: bool = True) -> list[Lead]:
        stmt = select(Lead).where(Lead.assigned_seller_id == employee_id)
        if open_only:
            stmt = stmt.where(Lead.stage.notin_(_CLOSED_STAGES))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_stale_open(self, threshold: datetime) -> list[Lead]:
        """13.3-band: ochiq lidlar, oxirgi aloqadan beri `threshold`dan oldin
        (`jobs/lead_follow_up_job.py`, kunlik)."""
        result = await self.session.execute(
            select(Lead).where(
                Lead.stage.notin_(_CLOSED_STAGES),
                Lead.last_contacted_at < threshold,
            )
        )
        return list(result.scalars().all())
