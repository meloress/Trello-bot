from sqlalchemy import select

from db.models.financial_suggestion import FinancialSuggestion
from db.repositories.base import BaseRepository
from utils.enums import FinancialSuggestionKind, FinancialSuggestionStatus


class FinancialSuggestionRepository(BaseRepository[FinancialSuggestion]):
    model = FinancialSuggestion

    async def list_pending_amount_entry(self) -> list[FinancialSuggestion]:
        """8.6-band admin UI: avtomatik bayroqlangan, lekin summa hali qo'lda
        kiritilmagan (`amount_withheld_by_customer IS NULL`) WAGE_DEDUCTION
        takliflari — `/moliyaviy` shu ro'yxatni ko'rsatadi."""
        result = await self.session.execute(
            select(FinancialSuggestion).where(
                FinancialSuggestion.kind == FinancialSuggestionKind.WAGE_DEDUCTION,
                FinancialSuggestion.status == FinancialSuggestionStatus.PENDING_MANAGER_REVIEW,
                FinancialSuggestion.amount_withheld_by_customer.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_pending(self) -> list[FinancialSuggestion]:
        """Mini App / kelajakdagi umumiy ko'rinish uchun: har ikkala tur
        (WAGE_DEDUCTION va ADVANCE_WAIVER) bo'yicha hali ko'rib chiqilmagan
        takliflar — `list_pending_amount_entry()`dan farqli, summa/foiz
        allaqachon ma'lum bo'lganlarni ham qamraydi (faqat status filtri)."""
        result = await self.session.execute(
            select(FinancialSuggestion).where(
                FinancialSuggestion.status == FinancialSuggestionStatus.PENDING_MANAGER_REVIEW,
            )
        )
        return list(result.scalars().all())

    async def exists_for_task(self, task_id: int, kind: FinancialSuggestionKind) -> bool:
        """8.6-band: bir xil task+kind uchun ikki marta avtomatik taklif
        yaratilmasligi uchun (`overdue_watch_job` har soat qayta tekshiradi)."""
        result = await self.session.execute(
            select(FinancialSuggestion.id).where(
                FinancialSuggestion.task_id == task_id,
                FinancialSuggestion.kind == kind,
            )
        )
        return result.scalar_one_or_none() is not None
