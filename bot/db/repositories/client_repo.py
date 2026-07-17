from sqlalchemy import select

from db.models.client import Client
from db.repositories.base import BaseRepository


class ClientRepository(BaseRepository[Client]):
    model = Client

    async def get_by_phone_number(self, phone_number: str) -> Client | None:
        """Vazifa yaratishda mavjud mijozni telefon bo'yicha topish (dublikat oldini olish)."""
        result = await self.session.execute(
            select(Client).where(Client.phone_number == phone_number)
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> Client | None:
        result = await self.session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()
