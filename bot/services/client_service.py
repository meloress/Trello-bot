"""Mijoz yozuvlarini boshqarish (12-band). Admin vazifa yaratishda telefon
raqami orqali mavjud mijozni topadi yoki yangisini yaratadi
(`find_or_create_client`); mijozning o'zi keyin `/mijoz` orqali shu telefon
raqamini kiritib `telegram_id`sini bog'laydi (`link_client_to_telegram` —
`registration_service.link_employee_to_telegram` bilan bir xil naqsh:
yangi yozuv bu yerda yaratilmaydi, faqat mavjudiga bog'lanadi)."""

from core.database import async_session
from db.models.client import Client
from db.repositories import ClientRepository


class ClientNotFoundError(Exception):
    """Berilgan telefon raqami bilan mijoz bazada topilmadi."""


class ClientAlreadyLinkedError(Exception):
    """Mijoz allaqachon boshqa Telegram akkauntga bog'langan."""


async def find_or_create_client(*, phone_number: str, full_name: str) -> Client:
    async with async_session() as session:
        repo = ClientRepository(session)
        client = await repo.get_by_phone_number(phone_number)
        if client is not None:
            if full_name and full_name != client.full_name:
                await repo.update(client, full_name=full_name)
            await session.commit()
            return client

        client = await repo.create(full_name=full_name, phone_number=phone_number)
        await session.commit()
        return client


async def link_client_to_telegram(phone_number: str, telegram_id: int) -> Client:
    """`phone_number` endi Telegram kontakti orqali keladi (aniq mos kelish
    o'rniga `find_by_normalized_phone` — admin turli formatda kiritgan
    bo'lishi mumkin, bu esa taqlid qilib bo'lmaydigan, Telegram tasdiqlagan
    raqam bilan solishtiradi)."""
    async with async_session() as session:
        repo = ClientRepository(session)
        client = await repo.find_by_normalized_phone(phone_number)
        if client is None:
            raise ClientNotFoundError(f"'{phone_number}' raqami bilan mijoz topilmadi")

        if client.telegram_id is not None and client.telegram_id != telegram_id:
            raise ClientAlreadyLinkedError(f"'{phone_number}' allaqachon boshqa Telegram akkauntga bog'langan")

        if client.telegram_id != telegram_id:
            await repo.update(client, telegram_id=telegram_id)
            await session.commit()

        return client
