"""Fasad sex TZ, Phase 8: kunlik rasm/video hisobot muvofiqligi — FAQAT
kuzatuv (kim yubordi/yubormadi), hech qanday jarima/ball hisoblanmaydi.
TZning o'zi bu masalada ochiq savol qoldirgan (`.claude/plans/09z-fasad-sex-
ochiq-savollar.md`), shu sabab `penalty_service.py`ga ATAYLAB tegilmagan.
"""

from datetime import date, datetime, timezone

from core.database import async_session
from db.models.daily_report_submission import DailyReportSubmission
from db.models.employee import Employee
from db.repositories import DailyReportSubmissionRepository, EmployeeRepository
from utils.formatters import TASHKENT_TZ


def today_tashkent() -> date:
    """Toshkent vaqti bo'yicha "bugun" — `reminder_job.py`dagi bilan bir xil
    `TASHKENT_TZ` asosida."""
    return datetime.now(TASHKENT_TZ).date()


async def submit_daily_report(
    employee_id: int, file_id: str, *, report_date: date | None = None
) -> DailyReportSubmission:
    """`UNIQUE(employee_id, report_date)` bo'yicha upsert: shu kunga xodimning
    birinchi yozuvi bo'lsa yaratiladi, qayta yuborilsa (masalan aniqroq video)
    mavjud qator YANGILANADI — tarix saqlanmaydi, faqat oxirgi holat kerak."""
    report_date = report_date or today_tashkent()
    async with async_session() as session:
        repo = DailyReportSubmissionRepository(session)
        existing = await repo.get_by_employee_and_date(employee_id, report_date)
        submitted_at = datetime.now(timezone.utc)
        if existing is not None:
            submission = await repo.update(existing, file_id=file_id, submitted_at=submitted_at)
        else:
            submission = await repo.create(
                employee_id=employee_id,
                report_date=report_date,
                file_id=file_id,
                submitted_at=submitted_at,
            )
        await session.commit()
        return submission


async def list_missing_for_date(report_date: date | None = None) -> list[Employee]:
    """`daily_report_required=True` FAOL xodimlar orasida shu kunga hali
    yozuvi yo'qlar (to'plam ayirmasi)."""
    report_date = report_date or today_tashkent()
    async with async_session() as session:
        required = await EmployeeRepository(session).list_daily_report_required()
        submissions = await DailyReportSubmissionRepository(session).list_by_date(report_date)
    submitted_ids = {s.employee_id for s in submissions}
    return [e for e in required if e.id not in submitted_ids]
