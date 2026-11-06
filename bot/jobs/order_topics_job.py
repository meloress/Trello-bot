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
from aiogram.types import BufferedInputFile

from config import settings
from core.database import async_session
from db.repositories import EmployeeRepository, OrderTopicRepository
from jobs import nazorat_trello_watch_job
from services import order_card_image, order_template
from trello.client import TrelloClient
from utils.enums import Role
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
# ertalab Trello/Telegram javob bermasa: 6 marta, 5 daqiqadan — 30 daqiqa
DAILY_ATTEMPTS, DAILY_RETRY_SECONDS = 6, 300
_HISTORY = "updateCard:idList,createCard,copyCard,moveCardToBoard,convertToCardFromCheckItem"


def _trello() -> TrelloClient:
    return TrelloClient(settings.trello_api_key, settings.trello_token)


def _since() -> datetime | None:
    since = settings.order_topics_since
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=TASHKENT_TZ)
    return since


async def _history(trello, card_id: str, cache: dict):
    """(ko'chishlar [(vaqt, list nomi)], qo'shilgan odamlar [(vaqt, member id, Trello'dagi ismi)]) — bitta so'rov."""
    if card_id not in cache:
        actions = await trello._request("GET", f"/cards/{card_id}/actions",
                                        params={"filter": _HISTORY + ",addMemberToCard", "limit": 1000})
        moves, adds = [], []
        for a in actions or []:
            at, data = datetime.fromisoformat(a["date"].replace("Z", "+00:00")), a.get("data") or {}
            if a.get("type") == "addMemberToCard":
                member = a.get("member") or {}
                adds.append((at, data.get("idMember") or member.get("id"), member.get("fullName") or "?"))
            else:
                moves.append((at, ((data.get("listAfter") or data.get("list") or {}).get("name") or "")))
        cache[card_id] = moves, adds
    return cache[card_id]


async def _staff() -> dict:
    """Trello member id -> (ism, rol) — botdagi hamma faol xodim."""
    async with async_session() as session:
        employees = await EmployeeRepository(session).list_active()
    return {e.trello_member_id: (e.full_name, e.role) for e in employees if e.trello_member_id}


async def _observers() -> list[int]:
    """Nazoratchi(lar) — kuzatuvchi roli (hozir Bahrom): kartalardagi kamchiliklar ro'yxati shularga."""
    async with async_session() as session:
        return [e.telegram_id for e in await EmployeeRepository(session).list_by_role(Role.OBSERVER) if e.telegram_id]


def _report_text(report: dict, today) -> str:
    sections = list(report.get("sections", []))
    if report.get("unknown"):
        sections.append(("Trello'da bor, lekin botda ro'yxatdan o'tmagan — ismi rasmda chiqmaydi",
                         [f"{name} — zakaz {', '.join(sorted(nums))}" for name, nums in sorted(report["unknown"].items())]))
    if report.get("failed"):
        sections.append(("Bugun rasmi yuborilmagan zakazlar (xato, ertaga qayta urinadi)", sorted(report["failed"])))
    if report.get("down"):
        sections.append(("Bugungi 08:00 hisobot UMUMAN ketmadi", ["Trello yoki Telegram 30 daqiqa davomida javob bermadi"]))
    if not sections:
        return ""
    parts = [f"⚠️ Zakaz kartalari — tuzatish kerak ({today:%d.%m})"]
    for title, lines in sections:
        parts.append(f"\n{title}:\n" + "\n".join(f"• {line}" for line in lines))
    return "\n".join(parts)


async def _notify_observers(bot: Bot, report: dict) -> None:
    text = _report_text(report, datetime.now(TASHKENT_TZ))
    if not text:
        return
    for chat in await _observers():
        for i in range(0, len(text), 4000):  # Telegram xabari 4096 belgigacha
            try:
                await bot.send_message(chat, text[i:i + 4000])
            except Exception:
                logger.exception("order_topics: nazoratchiga (%s) yuborilmadi", chat)


def _image(parts, now, staff):
    """(rasm yoki None, imzo, tugadi_mi, model). Rasm chizilmasa — eski matn yuboriladi."""
    model, signature, finished = order_template.order_view(parts, now, staff)
    try:
        return order_card_image.draw(model), signature, finished, model
    except Exception:
        logger.exception("order_topics: rasm chizilmadi — matn yuboriladi")
        return None, signature, finished, model


async def _open_new_topics(bot: Bot, chat_id: int, all_cards: list, rows: list, now: datetime,
                           list_names: dict) -> None:
    since = _since()
    tracked = {r.card_id for r in rows}
    # sana listidagi ("13 DEKABR") nusxa zakaz emas: u hech qachon skladga chiqmaydi -> topic hech yopilmasdi
    new = [(c["id"], c["name"]) for c in all_cards
           if not c.get("closed") and c["id"] not in tracked and order_template.card_created(c["id"]) >= since
           and not order_template.is_date_list(list_names.get(c.get("idList")))]
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
                  daily: bool, report: dict | None = None) -> int:
    async with async_session() as session:
        rows = [r for r in await OrderTopicRepository(session).list_all() if r.finished_at is None]
    by_number = {}
    for card in cards_by_id.values():
        by_number.setdefault(order_template.order_number(card["name"]), []).append(card["id"])
    # bitta zakaz (topic + raqam: korpus, FASAD, ...) — bitta rasm; polniy uy topicida har raqamga alohida
    groups = {}
    for row in rows:
        card = cards_by_id.get(row.card_id)
        number = (order_template.order_number(card["name"]) if card else None) or row.order_number
        groups.setdefault((row.thread_id, number), []).append((row, card))
    cache, people, sent, finished_threads = {}, None, 0, set()
    for (thread_id, number), members in groups.items():
        changes = {row.id: {} for row, _ in members}
        for row, card in members:
            if card is None:  # arxivlandi/o'chirildi — bu karta kuzatilmaydi
                changes[row.id]["finished_at"] = now
            elif number != row.order_number:  # karta raqami tahrirlandi (2669 -> 2696)
                changes[row.id]["order_number"] = number
        live = [(row, card) for row, card in members if card is not None]
        try:
            # tarix (Trello so'rovi) faqat kerak bo'lganda: ertalab, yangi karta, hamma kartasi skladga/keyin o'tganda
            if live and (daily or any(row.signature is None for row, _ in live) or all(
                    order_template.stage_kind(list_names.get(card.get("idList"))) in order_template.FINISH_KINDS
                    for _, card in live)):
                if people is None:
                    staff = await _staff()
                    # ism faqat ishchi/brigadirniki (sotuvchi ham kartada bo'ladi — u ko'rsatilmaydi)
                    people = {m: n for m, (n, role) in staff.items() if role in (Role.WORKER, Role.BRIGADIER)}
                parts, texts = [], []
                for _, card in live:
                    moves, adds = await _history(trello, card["id"], cache)
                    if report is not None:
                        for _, m, trello_name in adds:
                            if m not in staff:
                                report.setdefault("unknown", {}).setdefault(trello_name, set()).add(number)
                    siblings = [(await _history(trello, other, cache))[0]
                                for other in by_number.get(number, []) if other != card["id"]]
                    parts.append(order_template.analyze(card, moves, siblings, now,
                                                        [(at, people[m]) for at, m, _ in adds if m in people]))
                    texts.append(order_template.render(card, moves, siblings, now)[0])
                png, signature, finished, model = _image(parts, now, list(people.values()))
                # ertalab — hammaga; kun davomida — faqat yangi zakazning birinchi xabari va tugaganda
                # (mavjud zakazga qo'shilgan FASAD kartasi alohida xabar chiqarmaydi)
                if daily or all(row.signature is None for row, _ in live) or finished:
                    if sent:
                        await asyncio.sleep(SEND_GAP_SECONDS)
                    try:
                        if png:
                            await bot.send_photo(chat_id, BufferedInputFile(png, f"zakaz_{number}.png"),
                                                 caption=model["caption"][:1024], message_thread_id=thread_id)
                        else:
                            await bot.send_message(chat_id, "\n\n".join(texts)[:4096], message_thread_id=thread_id)
                    except TelegramBadRequest as e:
                        if "thread not found" not in str(e).lower():
                            raise
                        logger.warning("order_topics: topic %s guruhda o'chirilgan — zakaz %s kuzatilmaydi",
                                       thread_id, number)
                        finished = True
                    sent += 1
                for row, _ in live:
                    changes[row.id]["signature"] = signature
                    if finished:
                        changes[row.id]["finished_at"] = now
        except Exception:
            logger.exception("order_topics: zakaz %s yangilanmadi", number)
            if report is not None:
                report.setdefault("failed", []).append(str(number))
        for row, card in live:
            if row.topic_name and card["name"][:128] != row.topic_name:
                try:  # alohida: nom o'zgarmasa ham yuborilgan xabar saqlansin (aks holda qayta yuborilardi)
                    await bot.edit_forum_topic(chat_id, row.thread_id, name=card["name"][:128])
                    changes[row.id]["topic_name"] = card["name"][:128]
                except Exception:
                    logger.exception("order_topics: topic %s nomi o'zgarmadi", row.thread_id)
        for row, _ in members:
            if changes[row.id]:
                async with async_session() as session:
                    repo = OrderTopicRepository(session)
                    await repo.update(await repo.get_by_id(row.id), **changes[row.id])
                    await session.commit()
                if "finished_at" in changes[row.id]:
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
    """Ertalabki 08:00 hisobot: har bir ochiq zakaz o'z topiciga; keyin nazoratchiga
    kartalardagi kamchiliklar. Trello/Telegram javob bermasa — 30 daqiqa qayta uriniladi."""
    if not settings.order_group_chat_id or _since() is None:
        return 0
    for attempt in range(DAILY_ATTEMPTS):
        report = {}
        sent = await run(bot, trello_factory, daily=True, report=report)
        if sent is not None:
            await _notify_observers(bot, report)
            return sent
        logger.warning("order_topics: ertalabki hisobot %d-urinishda o'tmadi", attempt + 1)
        if attempt + 1 < DAILY_ATTEMPTS:
            await asyncio.sleep(DAILY_RETRY_SECONDS)
    await _notify_observers(bot, {"down": True})
    return 0


async def run(bot: Bot, trello_factory=_trello, daily: bool = False, report: dict | None = None) -> int | None:
    """Yuborilgan xabarlar soni; None — Trello/umumiy xato (hech narsa qilinmadi)."""
    chat_id = settings.order_group_chat_id
    if not chat_id or _since() is None:
        return 0
    async with _lock:
        return await _run(bot, chat_id, trello_factory, daily, report)


async def _run(bot: Bot, chat_id: int, trello_factory, daily: bool, report: dict | None = None) -> int | None:
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
            list_names = {lst["id"]: lst["name"] for lst in lists or []}
            async with async_session() as session:
                rows = await OrderTopicRepository(session).list_all()
            if report is not None:
                report["sections"] = order_template.name_issues(all_cards, list_names, _since(),
                                                                {r.card_id for r in rows})
            try:  # bitta topic ochilmasa ham (masalan Telegram rad etdi) mavjud zakazlar hisoboti to'xtamasin
                await _open_new_topics(bot, chat_id, all_cards, rows, now, list_names)
            except Exception:
                logger.exception("order_topics: yangi topic ochilmadi")
            return await _update(bot, chat_id, trello, {c["id"]: c for c in all_cards if not c.get("closed")},
                                 list_names, now, daily, report)
    except Exception:
        logger.exception("order_topics_job xatosi")
        return None
