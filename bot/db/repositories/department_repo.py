from sqlalchemy import select

from db.models.department import Department
from db.repositories.base import BaseRepository


class DepartmentRepository(BaseRepository[Department]):
    model = Department

    async def list_by_module(self, module: str) -> list[Department]:
        """Mebel moduli: `trello_ingest_job` faqat shu modulga tegishli
        bo'limlarni ko'rib chiqadi."""
        result = await self.session.execute(select(Department).where(Department.module == module))
        return list(result.scalars().all())

    async def get_by_trello_list_id(self, trello_list_id: str) -> Department | None:
        """Mebel moduli: karta qaysi Trello ro'yxatida ekanini bo'limga
        aylantirish (`trello_ingest_job`ning bosqich-o'tish aniqlashi)."""
        result = await self.session.execute(
            select(Department).where(Department.trello_list_id == trello_list_id)
        )
        return result.scalar_one_or_none()
