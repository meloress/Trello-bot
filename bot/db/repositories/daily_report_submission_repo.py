from datetime import date

from sqlalchemy import select

from db.models.daily_report_submission import DailyReportSubmission
from db.repositories.base import BaseRepository


class DailyReportSubmissionRepository(BaseRepository[DailyReportSubmission]):
    model = DailyReportSubmission

    async def get_by_employee_and_date(
        self, employee_id: int, report_date: date
    ) -> DailyReportSubmission | None:
        result = await self.session.execute(
            select(DailyReportSubmission).where(
                DailyReportSubmission.employee_id == employee_id,
                DailyReportSubmission.report_date == report_date,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_date(self, report_date: date) -> list[DailyReportSubmission]:
        result = await self.session.execute(
            select(DailyReportSubmission).where(DailyReportSubmission.report_date == report_date)
        )
        return list(result.scalars().all())
