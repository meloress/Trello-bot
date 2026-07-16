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

    async def get_by_brigadier_id(self, brigadier_id: int) -> Brigade | None:
        """11.1-band: brigadir o'zi boshqaradigan brigadani topadi."""
        result = await self.session.execute(
            select(Brigade).where(Brigade.brigadier_id == brigadier_id)
        )
        return result.scalar_one_or_none()
