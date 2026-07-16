from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import TimestampedBase

ModelType = TypeVar("ModelType", bound=TimestampedBase)


class BaseRepository(Generic[ModelType]):
    """CRUD'ning takrorlanadigan qismi. Har bir repository shundan meros oladi
    va faqat o'ziga xos so'rovlarni qo'shadi. Commit qilmaydi — bu unit-of-work
    (masalan, middlewares/db_session.py) zimmasida."""

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_: int) -> ModelType | None:
        return await self.session.get(self.model, id_)

    async def list_all(self) -> list[ModelType]:
        result = await self.session.execute(select(self.model))
        return list(result.scalars().all())

    async def create(self, **fields) -> ModelType:
        obj = self.model(**fields)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: ModelType, **fields) -> ModelType:
        for key, value in fields.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelType) -> None:
        await self.session.delete(obj)
        await self.session.flush()
