"""Rolga asoslangan ruxsat middleware'i (16-band, xavfsizlik: "rolga qarab
cheklangan ruxsatlar"). Faqat shu middleware ulangan routerlar himoyalanadi —
masalan admin buyruqlari (`handlers/admin/*`). Ruxsat berilgan xodim
handlerlarga `employee: Employee` parametri sifatida avtomatik uzatiladi,
har bir handler qayta so'rov yubormasin uchun.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.database import async_session
from db.repositories import EmployeeRepository
from utils.enums import Role

ACCESS_DENIED_TEXT = "Bu buyruq faqat rahbar/nazoratchi uchun."


class RoleAccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_roles: set[Role]) -> None:
        self._allowed_roles = allowed_roles

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_id = event.from_user.id if event.from_user else None

        employee = None
        if telegram_id is not None:
            async with async_session() as session:
                employee = await EmployeeRepository(session).get_by_telegram_id(telegram_id)

        if employee is None or employee.role not in self._allowed_roles:
            if isinstance(event, CallbackQuery):
                await event.answer(ACCESS_DENIED_TEXT, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(ACCESS_DENIED_TEXT)
            return None

        data["employee"] = employee
        return await handler(event, data)
