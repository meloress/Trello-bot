"""Nazorat Trello: zakaz va ball FAQAT Trello'dan (foydalanuvchi talabi:
"botdan unaqa ish qilinmasin, faqat trellodan"). Job "nazorat trello"
doskasining hodisalar jurnalini (`/boards/{id}/actions`) har daqiqada o'qiydi:

  - kartaga a'zo qo'shildi (`addMemberToCard`) — o'sha odamga muddati bilan
    xabar (`notify_trello_card_assigned`) va, ishchi/brigadir bo'lsa, uning
    shu kartadagi vaqti boshlanadi; eski odamning vaqti yopiladi;
  - a'zo olib tashlandi (`removeMemberFromCard`) — uning vaqti yopiladi;
  - karta arxivlandi (`updateCard:closed`) — hammaning vaqti yopiladi;
  - muddat o'zgardi (`updateCard:due`) — ochiq vaqtlarning muddati yangilanadi.

Vaqt yopilganda ball ESKI tizim bo'yicha yoziladi — qoidalar
`services/trello_hold_service.py` boshida. Bot Trello'ga HECH NARSA yozmaydi.

Doska alohida sozlanmaydi — Nazorat Trello bo'limlari qaysi doskaning
listlariga ulangan bo'lsa (`departments.trello_list_id`), o'sha kuzatiladi.

Kursor bazada (`app_settings.nazorat_trello_cursor`): deploydan keyin job
qolgan joyidan davom etadi, "olib tashlandi" hodisasi yo'qolmaydi (aks holda
ball umuman yozilmay qolardi). Birinchi ishga tushishda doskadagi eski
hodisalar o'tkazib yuboriladi — orqaga qarab hech kimga ball yozilmaydi.

ponytail: bitta so'rovda 1000 tagacha hodisa; bot uzoq to'xtab qolib undan
ko'p yig'ilsa, eng eskilari o'tkazib yuboriladi — kerak bo'lsa `before` bilan
sahifalash qo'shiladi.
"""

import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select

from config import settings
from core.database import async_session
from db.models.department import Department
from db.repositories import EmployeeRepository
from services import notification_service, settings_service, task_service, trello_hold_service as holds
from trello.client import TrelloClient
from utils.modules import NAZORAT_TRELLO

logger = logging.getLogger(__name__)

_FILTER = "addMemberToCard,removeMemberFromCard,updateCard:closed,updateCard:due"

_board_id: str | None = None


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


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _member(trello_member_id: str):
    """(xodim, tur): tur — ball oladigan ishchi/brigadir, boshqa xodim yoki
    botga bog'lanmagan Trello a'zosi."""
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_trello_member_id(trello_member_id)
    if employee is None:
        return None, holds.UNKNOWN
    if employee.is_active and employee.role in task_service.ASSIGNABLE_ROLES:
        return employee, holds.WORKER
    return employee, holds.OTHER


async def _close(bot, card_id: str, task_ids, at: datetime, card) -> None:
    started = {task_id: started_at for task_id, _, started_at in await holds.open_holds(card_id)}
    for task_id in task_ids:
        if task_id in started:
            await holds.close_hold(bot, task_id, at=at, deadline=_parse_dt(card.get("due")), started_at=started[task_id])


async def _handle(bot, trello, action) -> None:
    kind = action["type"]
    data = action.get("data") or {}
    card_id = (data.get("card") or {}).get("id")
    if not card_id:
        return
    at = _parse_dt(action["date"])
    card = await trello._request(
        "GET", f"/cards/{card_id}",
        params={"fields": "name,due,closed,idMembers", "list": "true", "list_fields": "name"},
    )

    if kind == "updateCard":
        if "due" in (data.get("old") or {}):
            await holds.set_card_deadline(card_id, _parse_dt((data.get("card") or {}).get("due")))
        if (data.get("card") or {}).get("closed") and "closed" in (data.get("old") or {}):
            await _close(bot, card_id, [task_id for task_id, _, _ in await holds.open_holds(card_id)], at, card)
        return

    member_id = data.get("idMember")
    if not member_id:
        return
    employee, member_kind = await _member(member_id)

    if kind == "removeMemberFromCard":
        if employee is not None:
            mine = [task_id for task_id, emp, _ in await holds.open_holds(card_id) if emp == employee.id]
            await _close(bot, card_id, mine, at, card)
        return

    # addMemberToCard
    current = await holds.open_holds(card_id)
    to_close, open_new = holds.plan_member_added(current, employee.id if employee else None, member_kind, at)
    await _close(bot, card_id, to_close, at, card)
    if open_new:
        await holds.open_hold(
            card_id=card_id, card_name=card["name"], employee=employee, started_at=at, deadline=_parse_dt(card.get("due")),
        )
    await notification_service.notify_trello_card_assigned(
        bot,
        trello_member_id=member_id,
        member_name=(action.get("member") or {}).get("fullName"),
        card_name=card["name"],
        list_name=(card.get("list") or {}).get("name"),
        due=_parse_dt(card.get("due")),
        card_member_ids=card.get("idMembers") or [],
    )


async def run(bot: Bot, trello_factory=None) -> int:
    """Qayta ishlangan hodisalar soni. `trello_factory` — test uchun soxta Trello."""
    global _board_id
    factory = trello_factory or (lambda: TrelloClient(settings.trello_api_key, settings.trello_token))
    handled = 0
    async with factory() as trello:
        if _board_id is None:
            _board_id = await _resolve_board_id(trello)
            if _board_id is None:
                logger.debug("nazorat_trello_watch_job: Trello listiga ulangan bo'lim yo'q — o'tkazib yuborildi")
                return 0

        path = f"/boards/{_board_id}/actions"
        cursor = await settings_service.get_trello_cursor()
        if cursor is None:
            # Birinchi ishga tushish: eski hodisalar qayta ishlanmaydi.
            latest = await trello._request("GET", path, params={"filter": _FILTER, "limit": 1, "fields": "date"})
            await settings_service.set_trello_cursor(
                latest[0]["date"] if latest else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            return 0

        actions = await trello._request(
            "GET", path,
            params={"filter": _FILTER, "since": cursor, "limit": 1000,
                    "fields": "type,date,data", "member": "true", "member_fields": "fullName"},
        )
        for action in sorted(actions or [], key=lambda a: a["date"]):
            if action["date"] <= cursor:
                continue
            try:
                await _handle(bot, trello, action)
                handled += 1
            except Exception:
                logger.exception("nazorat_trello_watch_job: hodisa xatosi (%s)", action.get("id"))
            # Xato bo'lsa ham oldinga: bitta buzuq karta butun navbatni to'xtatmasin.
            cursor = action["date"]
            await settings_service.set_trello_cursor(cursor)
    if handled:
        logger.info("nazorat_trello_watch_job: %s ta Trello hodisasi qayta ishlandi", handled)
    return handled
