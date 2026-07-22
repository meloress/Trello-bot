from sqlalchemy import select

from db.models.client import Client
from db.repositories.base import BaseRepository
from utils.formatters import normalize_phone


class ClientRepository(BaseRepository[Client]):
    model = Client

    async def get_by_phone_number(self, phone_number: str) -> Client | None:
        """Vazifa yaratishda mavjud mijozni telefon bo'yicha topish (dublikat oldini olish)."""
        result = await self.session.execute(
            select(Client).where(Client.phone_number == phone_number)
        )
        return result.scalar_one_or_none()

    async def find_by_normalized_phone(self, phone_number: str) -> Client | None:
        """12-band: `/mijoz` orqali Telegram kontakti kelganda moslashtirish —
        admin turli formatda kiritgan bo'lishi mumkin, shuning uchun aniq satr
        solishtirish o'rniga raqamlar bo'yicha solishtiriladi."""
        target = normalize_phone(phone_number)
        if not target:
            return None
        result = await self.session.execute(
            select(Client).where(Client.phone_number.is_not(None))
        )
        for client in result.scalars().all():
            if normalize_phone(client.phone_number) == target:
                return client
        return None

    async def get_by_telegram_id(self, telegram_id: int) -> Client | None:
        result = await self.session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()
