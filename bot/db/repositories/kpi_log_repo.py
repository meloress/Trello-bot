from datetime import datetime

from sqlalchemy import select

from db.models.kpi_log import KpiLog
from db.repositories.base import BaseRepository


class KpiLogRepository(BaseRepository[KpiLog]):
    model = KpiLog

    async def list_by_employee(self, employee_id: int) -> list[KpiLog]:
        """Xodim statistikasi/dashboard uchun ball tarixi, yangisidan eskisiga (10-band)."""
        result = await self.session.execute(
            select(KpiLog)
            .where(KpiLog.employee_id == employee_id)
            .order_by(KpiLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_employee_in_range(
        self, employee_id: int, since: datetime, until: datetime
    ) -> list[KpiLog]:
        """[since, until) yarim ochiq oraliqda, yangisidan eskisiga — oylik
        hisob-kitob va xodimning o'z ball tarixini ko'rish uchun (8.5-band)."""
        result = await self.session.execute(
            select(KpiLog)
            .where(
                KpiLog.employee_id == employee_id,
                KpiLog.created_at >= since,
                KpiLog.created_at < until,
            )
            .order_by(KpiLog.created_at.desc())
        )
        return list(result.scalars().all())
