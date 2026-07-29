from sqlalchemy import select

from db.models.brigade import Brigade
from db.repositories.base import BaseRepository


class BrigadeRepository(BaseRepository[Brigade]):
    model = Brigade

    async def list_by_department(self, department_id: int) -> list[Brigade]:
        result = await self.session.execute(
            select(Brigade).where(Brigade.department_id == department_id)
        )
        return list(result.scalars().all())

    async def list_by_brigadier_id(self, brigadier_id: int) -> list[Brigade]:
        """11.1-band: brigadir o'zi boshqaradigan brigadalar. RO'YXAT qaytaradi —
        bitta odam bir nechta bo'limga rahbarlik qilishi mumkin (masalan Kraska
        va Shkurka). Ilgari `scalar_one_or_none()` edi, ya'ni ikkinchi brigada
        paydo bo'lishi bilan `MultipleResultsFound` bilan qular edi."""
        result = await self.session.execute(
            select(Brigade).where(Brigade.brigadier_id == brigadier_id).order_by(Brigade.id)
        )
        return list(result.scalars().all())
