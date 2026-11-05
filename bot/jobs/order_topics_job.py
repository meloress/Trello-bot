"""Nazorat Trello: har bir yangi zakaz uchun superguruhda topic ochib, zakaz
shablonini (`services/order_template.py`) o'sha topicga yuborib turadi
(foydalanuvchi talabi, 2026-11-05 — avval buni bitta odam qo'lda qilardi).

  - yangi zakaz = `ORDER_TOPICS_SINCE` dan keyin yaratilgan, nomi zakaz
    formatidagi ("2553 Mijoz ... ( Sotuvchi ) 17.08 - 04.10") karta; topic
    nomi = karta nomi. Bir raqamli kartalar (FASAD + korpus) — bitta topic;
  - ismi+manzili bir xil 3+ zakaz birga tushsa — polniy uy, bitta topic;
  - shablon HAR KUNI ertalab 08:00 da har bir ochiq zakaz topiciga yuboriladi
    (`run_daily`); topic ochilganda birinchi xabar darhol, zakaz tugaganda
    oxirgi holat yuboriladi va topic yopiladi (5 daqiqalik `run`);
  - karta nomi o'zgarsa — topic nomi ham; zakaz skladga chiqsa — topic yopiladi.

Bot Trello'ga HECH NARSA yozmaydi. `ORDER_GROUP_CHAT_ID` yoki
`ORDER_TOPICS_SINCE` bo'lmasa job hech narsa qilmaydi. Guruh — "Topics"
yoqilgan superguruh, bot — "Manage topics" huquqli admin.

ponytail: har yurishda har ochiq zakaz kartasiga bitta Trello so'rovi — yuzlab
zakazda 5 daqiqalik intervalda ham Trello limitidan (100/10s) ancha past;
ko'payib ketsa doska hodisalar jurnalidan (`/boards/{id}/actions`) o'qishga o'tiladi.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from config import settings
from core.database import async_session
from db.repositories import OrderTopicRepository
from jobs import nazorat_trello_watch_job
from services import order_template
from trello.client import TrelloClient
from utils.formatters import TASHKENT_TZ

logger = logging.getLogger(__name__)

# polniy uy kartalari bir necha soniyada ochiladi — hammasi kelguncha kutiladi
SETTLE = timedelta(minutes=3)
# xabarlar orasidagi pauza — Telegram guruhga ~20 xabar/daqiqa (ertalab hammaga; polniy uy
# ochilganda 25 tagacha birinchi xabar birdan ketadi)
SEND_GAP_SECONDS = 3.5
# ertalabki (uzoq, pauzali) yurish bilan 5 daqiqalik yurish bir vaqtda ishlamasin:
# aks holda bitta zakazga ikki topic ochilardi yoki xabar ikki marta ketardi
_lock = asyncio.Lock()
_HISTORY = "updateCard:idList,createCard,copyCard,moveCardToBoard,convertToCardFromCheckItem"


def _trello() -> TrelloClient:
    return TrelloClient(settings.trello_api_key, settings.trello_token)


def _since() -> datetime | None:
    since = settings.order_topics_since
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=TASHKENT_TZ)
    return since


async def _history(trello, card_id: str, cache: dict):
    if card_id not in cache:
        actions = await trello._request("GET", f"/cards/{card_id}/actions",
                                        params={"filter": _HISTORY, "limit": 1000})
        cache[card_id] = [
            (datetime.fromisoformat(a["date"].replace("Z", "+00:00")),
             ((a.get("data") or {}).get("listAfter") or (a.get("data") or {}).get("list") or {}).get("name") or "")
            for a in actions or []
        ]
    return cache[card_id]


async def _open_new_topics(bot: Bot, chat_id: int, all_cards: list, rows: list, now: datetime) -> None:
    since = _since()
    tracked = {r.card_id for r in rows}
    new = [(c["id"], c["name"]) for c in all_cards
           if not c.get("closed") and c["id"] not in tracked and order_template.card_created(c["id"]) >= since]
    if not new or any(order_template.card_created(card_id) > now - SETTLE for card_id, _ in new):
        return  # kimdir hozir kartalar ochyapti — polniy uy bo'linib ketmasligi uchun hammasini kutamiz
    numbers = {r.order_number: r.thread_id for r in rows if r.order_number}
    houses = {r.house_key: r.thread_id for r in rows if r.house_key and r.finished_at is None}
    kept = order_template.new_orders(new, all_cards, since, set(numbers))
    join, create = order_template.plan_topics(kept, numbers, houses)
    names = dict(new)
    closed = {r.thread_id for r in rows} - {r.thread_id for r in rows if r.finished_at is None}
    async with async_session() as session:
        repo = OrderTopicRepository(session)
        for card_id, thread_id in join:
            await repo.create(card_id=card_id, order_number=order_template.order_number(names[card_id]),
                              thread_id=thread_id)
        await session.commit()
    for thread_id in {t for _, t in join} & closed:  # tugagan zakazga yangi karta (masalan ostatka) — topic qayta ochiladi
        try:
            await bot.reopen_forum_topic(chat_id, thread_id)
        except Exception:
            logger.exception("order_topics: topic %s qayta ochilmadi", thread_id)
    for title, house_key, card_ids in create:
        # har topic darhol saqlanadi — keyingisi xato bersa ham, ochilgani qayta ochilmaydi
        topic = await bot.create_forum_topic(chat_id, title)
        async with async_session() as session:
            repo = OrderTopicRepository(session)
            for card_id in card_ids:
                await repo.create(
                    card_id=card_id, order_number=order_template.order_number(names[card_id]),
                    thread_id=topic.message_thread_id, house_key=house_key,
                    topic_name=title if house_key is None and names[card_id][:128] == title else None,
                )
            await session.commit()
        logger.info("order_topics: topic ochildi %r (%d karta)", title, len(card_ids))


async def _update(bot: Bot, chat_id: int, trello, cards_by_id: dict, list_names: dict, now: datetime,
                  daily: bool) -> int:
    async with async_session() as session:
        rows = [r for r in await OrderTopicRepository(session).list_all()]
    by_number = {}
    for card in cards_by_id.values():
        by_number.setdefault(order_template.order_number(card["name"]), []).append(card["id"])
    cache, sent, finished_threads = {}, 0, set()
    for row in rows:
        if row.finished_at is not None:
            continue
        card = cards_by_id.get(row.card_id)
        changes = {}
        try:
            if card is None:  # arxivlandi/o'chirildi — kuzatuv tugadi
                changes["finished_at"] = now
            elif (daily or row.signature is None
                  or order_template.stage_kind(list_names.get(card.get("idList"))) in order_template.FINISH_KINDS):
                # tarix (Trello so'rovi) faqat kerak bo'lganda: ertalab, birinchi xabar, karta skladga/keyin o'tganda
                events = await _history(trello, card["id"], cache)
                siblings = [await _history(trello, other, cache)
                            for other in by_number.get(row.order_number, []) if other != card["id"]]
                text, signature, finished = order_template.render(card, events, siblings, now)
                # ertalab — hammaga; kun davomida — faqat yangi topicning birinchi xabari va tugaganda
                if daily or row.signature is None or finished:
                    if sent:
                        await asyncio.sleep(SEND_GAP_SECONDS)
                    try:
                        await bot.send_message(chat_id, text, message_thread_id=row.thread_id)
                    except TelegramBadRequest as e:
                        if "thread not found" not in str(e).lower():
                            raise
                        logger.warning("order_topics: topic %s guruhda o'chirilgan — karta %s kuzatilmaydi",
                                       row.thread_id, row.card_id)
                        finished = True
                    changes["signature"] = signature
                    sent += 1
                if finished:
                    changes["finished_at"] = now
        except Exception:
            logger.exception("order_topics: karta %s yangilanmadi", row.card_id)
            continue
        if card is not None and row.topic_name and card["name"][:128] != row.topic_name:
            try:  # alohida: nom o'zgarmasa ham yuborilgan xabar saqlansin (aks holda qayta yuborilardi)
                await bot.edit_forum_topic(chat_id, row.thread_id, name=card["name"][:128])
                changes["topic_name"] = card["name"][:128]
            except Exception:
                logger.exception("order_topics: topic %s nomi o'zgarmadi", row.thread_id)
        if changes:
            async with async_session() as session:
                repo = OrderTopicRepository(session)
                await repo.update(await repo.get_by_id(row.id), **changes)
                await session.commit()
            if "finished_at" in changes:
                finished_threads.add(row.thread_id)

    # topicdagi hamma zakaz tugagan bo'lsa — yopiladi (o'chirilmaydi, tarix qoladi)
    if finished_threads:
        async with async_session() as session:
            rows = await OrderTopicRepository(session).list_all()
        for thread_id in finished_threads:
            if all(r.finished_at is not None for r in rows if r.thread_id == thread_id):
                try:
                    await bot.close_forum_topic(chat_id, thread_id)
                except Exception:
                    logger.exception("order_topics: topic %s yopilmadi", thread_id)
    return sent


async def run_daily(bot: Bot, trello_factory=_trello) -> int:
    """Ertalabki 08:00 hisobot: har bir ochiq zakaz o'z topiciga."""
    return await run(bot, trello_factory, daily=True)


async def run(bot: Bot, trello_factory=_trello, daily: bool = False) -> int:
    """Yuborilgan xabarlar sonini qaytaradi."""
    chat_id = settings.order_group_chat_id
    if not chat_id or _since() is None:
        return 0
    async with _lock:
        return await _run(bot, chat_id, trello_factory, daily)


async def _run(bot: Bot, chat_id: int, trello_factory, daily: bool) -> int:
    now = datetime.now(timezone.utc)
    try:
        async with trello_factory() as trello:
            board_id = await nazorat_trello_watch_job._resolve_board_id(trello)
            if not board_id:
                return 0
            # arxivdagilar ham kerak: raqam avval ishlatilganmi (eski zakaz nusxasimi) — shulardan bilinadi
            all_cards = await trello._request("GET", f"/boards/{board_id}/cards/all",
                                              params={"fields": "name,labels,idList,closed"})
            lists = await trello._request("GET", f"/boards/{board_id}/lists",
                                          params={"filter": "all", "fields": "name"})
            async with async_session() as session:
                rows = await OrderTopicRepository(session).list_all()
            await _open_new_topics(bot, chat_id, all_cards, rows, now)
            return await _update(bot, chat_id, trello, {c["id"]: c for c in all_cards if not c.get("closed")},
                                 {lst["id"]: lst["name"] for lst in lists or []}, now, daily)
    except Exception:
        logger.exception("order_topics_job xatosi")
        return 0
