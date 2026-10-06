"""Nazorat Trello: zakaz FAQAT Trello'da beriladi (2026-10-06, foydalanuvchi
talabi: "botdan unaqa ish qilinmasin, faqat trellodan"). Bu job "nazorat
trello" doskasining hodisalar jurnalini (`/boards/{id}/actions`) har daqiqada
o'qiydi va kartaga a'zo qo'shilganini (`addMemberToCard`) ko'rsa —
`notification_service.notify_trello_card_assigned()` orqali o'sha ishchiga
muddati bilan, bo'limsiz nazoratchi va kuzatuvchilarga esa umumiy xabar.

Faqat XABAR: vazifa yaratmaydi, ball/jarima yozmaydi, kartaga tegmaydi.

Doska alohida sozlanmaydi — Nazorat Trello bo'limlari qaysi doskaning
listlariga ulangan bo'lsa (`departments.trello_list_id`), o'sha kuzatiladi.

Hodisa jurnali ishlatilgani uchun holat saqlash jadvali kerak emas va
doskadagi minglab eski kartalar umuman ko'rib chiqilmaydi — bot ishga
tushgandan KEYINGI hodisalargina xabar beradi.

ponytail: kursor xotirada — deploy/qayta ishga tushish paytidagi bir-ikki
daqiqalik hodisalar xabarsiz qoladi. Muhim bo'lsa kursorni `app_settings`ga
yozish kerak (migratsiya).
"""

import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select

from config import settings
from core.database import async_session
from db.models.department import Department
from services import notification_service
from trello.client import TrelloClient
from utils.modules import NAZORAT_TRELLO

logger = logging.getLogger(__name__)

_board_id: str | None = None
# Oxirgi qayta ishlangan hodisaning vaqti (Trello ISO matni). None = hali
# birinchi yurish bo'lmagan.
_cursor: str | None = None


async def _resolve_board_id(trello) -> str | None:
    async with async_session() as session:
        list_id = (
            await session.execute(
                select(Department.trello_list_id)
                .where(Department.module == NAZORAT_TRELLO, Department.trello_list_id.isnot(None))
                .limit(1)
            )
        ).scalar()
    if not list_id:
        return None
    return (await trello._request("GET", f"/lists/{list_id}", params={"fields": "idBoard"}))["idBoard"]


def _parse_due(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def run(bot: Bot, trello_factory=None) -> int:
    """Yuborilgan xabarlar soni (hodisalar bo'yicha). `trello_factory` —
    test uchun soxta Trello mijozi."""
    global _board_id, _cursor
    factory = trello_factory or (lambda: TrelloClient(settings.trello_api_key, settings.trello_token))
    sent = 0
    async with factory() as trello:
        if _board_id is None:
            _board_id = await _resolve_board_id(trello)
            if _board_id is None:
                logger.debug("nazorat_trello_watch_job: Trello listiga ulangan bo'lim yo'q — o'tkazib yuborildi")
                return 0

        path = f"/boards/{_board_id}/actions"
        if _cursor is None:
            # Birinchi yurish: eski hodisalar qayta yuborilmaydi, faqat kursor qo'yiladi.
            latest = await trello._request("GET", path, params={"filter": "addMemberToCard", "limit": 1, "fields": "date"})
            _cursor = latest[0]["date"] if latest else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            return 0

        actions = await trello._request(
            "GET", path,
            params={"filter": "addMemberToCard", "since": _cursor, "limit": 1000,
                    "fields": "date,data", "member": "true", "member_fields": "fullName"},
        )
        for action in sorted(actions or [], key=lambda a: a["date"]):
            if action["date"] <= _cursor:
                continue
            _cursor = action["date"]
            data = action.get("data") or {}
            card_id = (data.get("card") or {}).get("id")
            member_id = data.get("idMember")
            if not card_id or not member_id:
                continue
            try:
                card = await trello._request(
                    "GET", f"/cards/{card_id}",
                    params={"fields": "name,due,closed", "list": "true", "list_fields": "name"},
                )
                await notification_service.notify_trello_card_assigned(
                    bot,
                    trello_member_id=member_id,
                    member_name=(action.get("member") or {}).get("fullName"),
                    card_name=card["name"],
                    list_name=(card.get("list") or {}).get("name"),
                    due=_parse_due(card.get("due")),
                )
                sent += 1
            except Exception:
                logger.exception("nazorat_trello_watch_job: hodisa xatosi (card=%s, member=%s)", card_id, member_id)
    if sent:
        logger.info("nazorat_trello_watch_job: %s ta 'zakaz berildi' hodisasi xabar qilindi", sent)
    return sent


async def _demo() -> None:
    """Soxta Trello + soxta xabar bilan: birinchi yurish jim, keyingisi faqat yangi hodisani yuboradi."""
    global _board_id, _cursor
    calls = []

    class FakeTrello:
        def __init__(self, actions):
            self.actions = actions

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def _request(self, method, path, params=None):
            if path.endswith("/actions"):
                return self.actions[:1] if params.get("limit") == 1 else self.actions
            return {"name": "Zakaz 2601", "due": "2026-10-09T10:00:00.000Z", "list": {"name": "Abdulloh kroy chizish 24"}}

    async def fake_notify(bot, **kw):
        calls.append(kw)

    old = notification_service.notify_trello_card_assigned
    notification_service.notify_trello_card_assigned = fake_notify
    try:
        _board_id, _cursor = "board", None
        old_action = {"date": "2026-10-06T08:00:00.000Z", "data": {"card": {"id": "c0"}, "idMember": "m0"}}
        assert await run(None, lambda: FakeTrello([old_action])) == 0 and calls == [], "birinchi yurish eski hodisani yubordi"
        new_action = {"date": "2026-10-06T09:00:00.000Z", "data": {"card": {"id": "c1"}, "idMember": "m1"},
                      "member": {"fullName": "Abdulloh"}}
        assert await run(None, lambda: FakeTrello([new_action, old_action])) == 1
        assert calls[0]["trello_member_id"] == "m1" and calls[0]["card_name"] == "Zakaz 2601"
        assert calls[0]["due"] == datetime(2026, 10, 9, 10, tzinfo=timezone.utc)
        assert await run(None, lambda: FakeTrello([new_action, old_action])) == 0, "bitta hodisa ikki marta yuborildi"
        print("nazorat_trello_watch_job: OK")
    finally:
        notification_service.notify_trello_card_assigned = old
        _board_id, _cursor = None, None


if __name__ == "__main__":
    import asyncio

    asyncio.run(_demo())
