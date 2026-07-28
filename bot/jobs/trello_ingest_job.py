"""Mebel moduli: Trello -> bot bir tomonlama sinxronizatsiya.

Bot Trello'ga HECH QACHON yozmaydi (bu jobda bironta yozish metodi
chaqirilmaydi — faqat `/boards/{id}/lists` va `/lists/{id}/cards` o'qiladi).

## Doskani qanday "tushunadi"

Bazada bironta Trello ro'yxati ID'si saqlanmaydi. Har pollda doskadagi
ro'yxatlar qaytadan o'qiladi va NOMIGA qarab tasniflanadi
(`services/trello_board_map.py`):

  ISH (WORK)   — brigadaning ish ro'yxati ("Zoxid shpon brigada",
                 "kraska ELYOR 72 soat"). Karta bu yerga tushdi = ish
                 BOSHLANDI: vazifa ochiladi, kartadagi BARCHA tanish ishchiga
                 xabar boradi, taymer ketadi.
  KUTISH (QUEUE) — kutish/o'tish ro'yxati ("shpon hali boshlanmadik",
                 "shkurkadan chiqqan ...", "dastavka", "ustanovka"). Bu yerda
                 hech qanday vazifa OCHILMAYDI. Agar karta uchun ochiq vazifa
                 bo'lsa — demak karta ish ro'yxatidan chiqib ketgan, ya'ni
                 o'sha bosqich TUGAGAN: vazifa avtomatik yakunlanadi, ball
                 hisoblanadi va egasiga xabar boradi.

Natijada Trello'da yangi brigada ro'yxati qo'shilsa yoki o'chirilsa, yoki nomi
o'zgarsa — bazada hech narsa sozlash kerak emas. Trello hisobi almashtirilsa
faqat `app_settings.mebel_trello_board_id` yangilanadi.

## Muddat

1. Kartaning O'Z `due` sanasi bo'lsa — o'sha ishlatiladi (aniq ko'rsatma ustun).
2. Bo'lmasa — ro'yxat NOMIDAGI soat ("... 72 soat" -> hozir + 72 soat).
3. Ikkalasi ham bo'lmasa — vazifa OCHILMAYDI, karta kutadi (jurnalga yoziladi).
   Foydalanuvchi Trello'da ro'yxat nomiga soat qo'shsa yoki kartaga due sana
   qo'ysa — keyingi pollda o'zi ishga tushadi.

## Yakunlash — ikki yo'l birga

- Avtomatik: karta ish ro'yxatidan chiqib kutish ro'yxatiga o'tsa (yuqoriga q.).
- Qo'lda: brigadir Mini App'dan "Yakunlash" so'rovi yuboradi, rahbar
  tasdiqlaydi (`services/claim_service.py`). Bunda vazifa allaqachon COMPLETED
  bo'ladi va karta hali ish ro'yxatida tursa ham qaytadan ochilmaydi.

`core/scheduler.py` orqali har 5 daqiqada (`main.py`da ro'yxatdan o'tkaziladi).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from sqlalchemy import select

from config import settings
from core.database import async_session
from db.models.task import Task
from db.repositories import DepartmentRepository, EmployeeRepository, TaskAssignmentRepository, TaskRepository
from services import notification_service, penalty_service, settings_service, task_service, timer_service
from services.trello_board_map import build_board_map
from trello.client import TrelloClient
from utils.enums import TaskStatus, TrelloListKind

logger = logging.getLogger(__name__)


def _parse_due(card: dict) -> datetime | None:
    due_raw = card.get("due")
    if not due_raw:
        return None
    return datetime.fromisoformat(due_raw)


def _resolve_deadline(card: dict, hours: int | None) -> datetime | None:
    """Kartaning o'z `due` sanasi ustun; bo'lmasa ro'yxat nomidagi soatdan."""
    due = _parse_due(card)
    if due is not None:
        return due
    if hours:
        return datetime.now(timezone.utc) + timedelta(hours=hours)
    return None


async def _resolve_employee_ids(member_trello_ids: list[str]) -> list[int]:
    """Trello a'zo ID'larini tanish, FAOL, ijrochi bo'la oladigan xodimlarga
    aylantiradi (admin/sotuvchi kartada bo'lsa ham ijrochi hisoblanmaydi —
    `task_service.ASSIGNABLE_ROLES`)."""
    if not member_trello_ids:
        return []
    async with async_session() as session:
        repo = EmployeeRepository(session)
        found = []
        for trello_member_id in member_trello_ids:
            employee = await repo.get_by_trello_member_id(trello_member_id)
            if employee is not None and employee.is_active and employee.role in task_service.ASSIGNABLE_ROLES:
                found.append(employee.id)
        return found


async def _open_card_ids() -> set[str]:
    """Hozir OCHIQ (COMPLETED emas) vazifasi bor kartalarning ID to'plami —
    poll boshida BIR MARTA o'qiladi.

    Nega kerak: doskadagi kartalarning katta qismi kutish ro'yxatlarida turadi
    ("ustanovka ishlanvotti" yolg'iz o'zi 400+ karta) va ularning deyarli
    hech qaysisida ochiq vazifa yo'q. Har karta uchun alohida baza so'rovi
    qilinsa, bitta poll yuzlab so'rovga aylanadi va 5 daqiqalik oraliqqa
    sig'may qoladi. Shu to'plam bilan kutish ro'yxatidagi karta bazaga
    umuman murojaat qilmasdan o'tkazib yuboriladi."""
    async with async_session() as session:
        rows = await session.execute(
            select(Task.trello_card_id).where(
                Task.trello_card_id.isnot(None), Task.status != TaskStatus.COMPLETED
            )
        )
    return {row[0] for row in rows}


async def _open_task_for_card(card_id: str):
    """Shu karta uchun ochiq (COMPLETED emas) vazifa — bo'lmasa None."""
    async with async_session() as session:
        latest = await TaskRepository(session).get_latest_by_trello_card_id(card_id)
    if latest is None or latest.status == TaskStatus.COMPLETED:
        return None
    return latest


async def _finish_open_task(bot: Bot, card_id: str, why: str) -> None:
    """Karta ish ro'yxatidan chiqdi (yoki arxivlandi) — ochiq vazifani
    yakunlaydi, ball hisoblaydi va egasiga xabar yuboradi. Ochiq vazifa
    bo'lmasa jim o'tadi (kutish ro'yxatida turgan kartalarning ko'pchiligi
    aynan shunday — ular uchun hech qachon vazifa ochilmagan)."""
    task = await _open_task_for_card(card_id)
    if task is None:
        return
    logger.info("trello_ingest_job: vazifa %s avtomatik yakunlanmoqda (%s)", task.id, why)
    await penalty_service.finalize_task_and_apply_penalty(bot, task.id, finished_at=None)


def _is_before_cutoff(card: dict, start_at: datetime | None) -> bool:
    """Karta ingest chegarasidan OLDIN oxirgi marta qimirlaganmi.

    Chegara qo'yilgan bo'lsa, undan eski kartalar butunlay chetlab o'tiladi —
    doskada yillar davomida qotib qolgan eski buyurtmalar tizim yoqilgan
    zahoti ommaviy ravishda "yangi ish" bo'lib ochilib ketmasligi uchun.
    Karta Trello'da qimirlashi bilan (ko'chirilsa, a'zo qo'shilsa)
    `dateLastActivity` yangilanadi va karta o'zi oqimga qo'shiladi."""
    if start_at is None:
        return False
    raw = card.get("dateLastActivity")
    if not raw:
        return False  # ma'lumot yo'q — chetlab o'tmaymiz (yolg'on to'sishdan ko'ra o'tkazgan afzal)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")) < start_at
    except ValueError:
        return False


async def _start_work(
    bot: Bot, department, card: dict, hours: int | None, list_id: str, start_at: datetime | None = None
) -> None:
    """Karta bo'limning ISH ro'yxatida ko'rindi, lekin bazada ochiq vazifa
    yo'q -> yangi bosqich ochiladi."""
    if _is_before_cutoff(card, start_at):
        logger.debug(
            "trello_ingest_job: karta %s ingest chegarasidan eski (%s) — o'tkazib yuborildi",
            card["id"], card.get("dateLastActivity"),
        )
        return

    deadline = _resolve_deadline(card, hours)
    if deadline is None:
        logger.warning(
            "trello_ingest_job: karta %s uchun muddat aniqlanmadi "
            "(kartada due yo'q, '%s' ro'yxati nomida ham soat yo'q) — kutilmoqda",
            card["id"], card.get("_list_name", list_id),
        )
        return

    previous = None
    async with async_session() as session:
        latest = await TaskRepository(session).get_latest_by_trello_card_id(card["id"])
        if latest is not None:
            previous = latest.id

    new_task = await task_service.sync_trello_card_stage(
        department_id=department.id,
        card_id=card["id"],
        title=card["name"],
        description=card.get("desc"),
        deadline=deadline,
        member_trello_ids=card.get("idMembers") or [],
        previous_task_id=previous,
        trello_list_id=list_id,
    )
    if new_task is None:
        return  # kartada tanish ijrochi yo'q — jurnalga task_service yozgan
    try:
        await notification_service.notify_task_started(bot, new_task.id)
    except Exception:
        logger.exception("trello_ingest_job: notify_task_started xatosi (task_id=%s)", new_task.id)


async def _sync_open_task(bot: Bot, task, card: dict, hours: int | None, list_id: str) -> None:
    """Karta o'sha bo'limning ish ro'yxatida, vazifa allaqachon ochiq —
    a'zolar/muddat o'zgarganini tekshiramiz."""
    member_ids = card.get("idMembers") or []
    resolved = await _resolve_employee_ids(member_ids)

    new_assignees: list[int] = []
    previous_assignees: list[int] = []
    deadline_changed = False

    async with async_session() as session:
        task_repo = TaskRepository(session)
        fresh = await task_repo.get_by_id(task.id)
        if fresh is None:
            return

        if set(member_ids) != set(fresh.trello_last_seen_member_ids or []) and resolved:
            current = [a.employee_id for a in await TaskAssignmentRepository(session).list_by_task(fresh.id)]
            if set(resolved) != set(current):
                new_assignees = resolved
                previous_assignees = [e for e in current if e not in resolved]

        deadline = _resolve_deadline(card, hours) if card.get("due") else None
        if deadline is not None and fresh.deadline != deadline:
            await task_repo.update(fresh, deadline=deadline)
            deadline_changed = True

        await task_repo.update(
            fresh,
            trello_last_seen_list_id=list_id,
            trello_last_seen_member_ids=list(member_ids),
            trello_last_polled_at=datetime.now(timezone.utc),
        )
        await session.commit()

    if new_assignees:
        # Brigadir Trello'da ishchi(lar)ni kartaga qo'shdi = ishni bo'lib berdi.
        await task_service.set_assignees_from_trello(task.id, new_assignees)
        try:
            await notification_service.notify_task_started(bot, task.id)
        except Exception:
            logger.exception("trello_ingest_job: notify_task_started xatosi (task_id=%s)", task.id)
        for old_employee_id in previous_assignees:
            try:
                await notification_service.notify_task_delegated_via_trello(bot, task.id, old_employee_id)
            except Exception:
                logger.exception(
                    "trello_ingest_job: notify_task_delegated_via_trello xatosi (task_id=%s, employee_id=%s)",
                    task.id, old_employee_id,
                )

    if deadline_changed:
        await timer_service.reopen_if_overdue(task.id, (await _open_task_for_card(card["id"])).deadline)


async def _process_card(
    bot: Bot, entry: dict, card: dict, start_at: datetime | None = None,
    open_card_ids: set[str] | None = None,
) -> None:
    card_id = card["id"]
    # Ochiq vazifasi yo'q karta uchun bazaga umuman tegmaymiz. Bu yerda
    # tejash juda muhim: Railway Postgres'ga har yangi sessiya ~1.5 soniya
    # turadi, doskada esa 600+ karta bor — filtrsiz bitta poll 3 daqiqadan
    # oshib, 5 daqiqalik oraliqni to'ldirib qo'yardi.
    #   - arxivlangan karta -> yakunlash uchun OCHIQ vazifa kerak, yo'q ekan, ish yo'q;
    #   - kutish ro'yxati    -> u yerda vazifa umuman ochilmaydi.
    # Faqat ISH ro'yxatidagi arxivlanmagan karta bazaga boradi (yangi ish
    # ochilishi mumkin) — bular doskadagi kartalarning kichik qismi.
    if open_card_ids is not None and card_id not in open_card_ids:
        if card.get("closed") or entry["kind"] is TrelloListKind.QUEUE:
            return

    if card.get("closed"):
        await _finish_open_task(bot, card_id, "karta arxivlandi")
        return

    if entry["kind"] is TrelloListKind.QUEUE:
        # Kutish ro'yxati: bu yerda ish ochilmaydi. Karta bu yerda ko'rindi-yu
        # ochiq vazifasi bor bo'lsa — demak ish ro'yxatidan chiqib ketgan.
        await _finish_open_task(bot, card_id, f"karta '{entry['name']}' kutish ro'yxatiga o'tdi")
        return

    department = entry["department"]
    open_task = await _open_task_for_card(card_id)

    if open_task is None:
        async with async_session() as session:
            latest = await TaskRepository(session).get_latest_by_trello_card_id(card_id)
        # Shu bo'limda allaqachon yakunlangan va karta hali ko'chirilmagan —
        # (masalan Mini App'dan erta yakunlangan) qaytadan ochilmaydi.
        if latest is not None and latest.current_department_id == department.id:
            return
        await _start_work(bot, department, card, entry["hours"], entry["id"], start_at)
        return

    if open_task.current_department_id != department.id:
        # Karta boshqa bosqichning ish ro'yxatiga ko'chgan, lekin oldingi
        # bosqich hali yopilmagan — avval uni yakunlaymiz, keyin yangisini
        # ochamiz (jismoniy voqelik: ish allaqachon keyingi bosqichda).
        await _finish_open_task(bot, card_id, f"karta '{entry['name']}' ro'yxatiga ko'chdi")
        await _start_work(bot, department, card, entry["hours"], entry["id"], start_at)
        return

    await _sync_open_task(bot, open_task, card, entry["hours"], entry["id"])


async def run(bot: Bot) -> None:
    """Scheduler shu funksiyani chaqiradi. Bitta ro'yxat/kartadagi xatolik
    qolganlarini to'xtatmaydi — har biri alohida try/except ichida."""
    app_settings = await settings_service.get_settings()
    board_id = (app_settings.mebel_trello_board_id or "").strip()
    start_at = app_settings.mebel_ingest_start_at
    if not board_id:
        logger.debug("trello_ingest_job: mebel_trello_board_id sozlanmagan — o'tkazib yuborildi")
        return

    async with async_session() as session:
        departments = await DepartmentRepository(session).list_by_module("mebel")
    departments = [d for d in departments if (d.trello_list_keywords or "").strip()]
    if not departments:
        logger.debug("trello_ingest_job: kalit so'zi sozlangan mebel bo'limi yo'q — o'tkazib yuborildi")
        return

    processed = failed = 0
    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        try:
            lists = await trello._request("GET", f"/boards/{board_id}/lists", params={"fields": "name"})
        except Exception:
            logger.exception("trello_ingest_job: doska %s ro'yxatlarini o'qib bo'lmadi", board_id)
            return

        open_card_ids = await _open_card_ids()
        board_map = build_board_map(lists, departments)
        work_count = sum(1 for e in board_map if e["kind"] is TrelloListKind.WORK)

        # Ro'yxatlar PARALLEL o'qiladi: ketma-ket so'ralganda 25 ta ro'yxat
        # 3 daqiqadan ortiq vaqt olardi va 5 daqiqalik oraliqqa zo'rg'a
        # sig'ardi. Semafor bilan bir vaqtda 5 tadan — Trello API'ni
        # bo'g'masdan, lekin sezilarli tez.
        semaphore = asyncio.Semaphore(5)

        async def _fetch(entry):
            async with semaphore:
                try:
                    return entry, await trello.list_cards_in_list(entry["id"])
                except Exception:
                    logger.exception(
                        "trello_ingest_job: '%s' ro'yxati kartalarini o'qishda xatolik", entry["name"]
                    )
                    return entry, None

        fetched = await asyncio.gather(*(_fetch(e) for e in board_map))

        for entry, cards in fetched:
            if cards is None:
                failed += 1
                continue

            for card in cards:
                try:
                    await _process_card(bot, entry, card, start_at, open_card_ids)
                    processed += 1
                except Exception:
                    logger.exception(
                        "trello_ingest_job: karta %s ('%s') qayta ishlashda xatolik",
                        card.get("id"), entry["name"],
                    )
                    failed += 1

    logger.info(
        "trello_ingest_job yakunlandi: %s karta, %s xatolik "
        "(%s ro'yxat: %s ish + %s kutish, %s bo'lim)",
        processed, failed, len(board_map), work_count, len(board_map) - work_count, len(departments),
    )
