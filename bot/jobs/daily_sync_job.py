"""Trello <-> baza sinxronizatsiyasi (6.3-band): Trello'ning o'zida avtomatik
status kuzatuvi yo'q, shuning uchun bu job hali yakunlanmagan har bir vazifani
Trello bilan solishtiradi:
  - karta nomi o'zgargan bo'lsa -> `tasks.title` yangilanadi;
  - karta arxivlangan (`closed=true`) bo'lsa -> vazifa `timer_service.finish_task()`
    orqali xuddi botdan "Yakunlash" bosilgandek yopiladi — shu jumladan
    `penalty_service` orqali kechikish tekshiruvi HAM ishga tushadi. Buni
    ataylab shunday qildik: aks holda kimdir Trello'da kartani to'g'ridan-to'g'ri
    arxivlab, KPI tizimini butunlay chetlab o'tishi mumkin bo'lardi — bu
    loyihaning asosiy maqsadiga (0-band: ishlamayotgan xodimni AVTOMATIK
    aniqlash) zid bo'lardi;
  - hali OCHIQ (arxivlanmagan) karta bo'lsa -> `trello_sync_service` orqali
    muddatga mos LABEL (yashil/sariq/qizil) qo'yiladi (6.3-band).

`core/scheduler.py` orqali har kuni 01:00da (Asia/Tashkent) ishga tushiriladi.
"""

import logging

from aiogram import Bot

from config import settings
from core.database import async_session
from db.models.task import Task
from db.repositories import TaskRepository
from services import penalty_service, trello_sync_service
from trello.client import TrelloAPIError, TrelloClient
from utils.enums import TaskStatus
from utils.modules import MEBEL

logger = logging.getLogger(__name__)


async def _list_open_tasks() -> list[Task]:
    """Faqat ORDER turidagi vazifalar — MISC vazifalarda (9-band) Trello
    karta umuman yo'q, shuning uchun bu job ularni ko'rib chiqmaydi.
    `PENDING_SETUP` (6.1/7.4-band: keyingi bo'limga kelgan, hali muddat/xodim
    belgilanmagan bosqich — `deadline=NULL`) ham chetlab o'tiladi: bu holatda
    `determine_status()` NULL deadline bilan chaqirilib yiqilardi, va muddat
    hali yo'qligi sabab label/muddat tekshiruvi umuman ma'nosiz. ACTIVE va
    STOPPED (deadline bor, faqat taymer muzlatilgan) — avvalgidek qamrovda.

    Mebel moduli (`departments.module == "mebel"`) endi bu ro'yxatdan
    CHIQARIB TASHLANADI — bu modul endi Trello'ni bevosita,
    `jobs/trello_ingest_job.py` orqali (har 5 daqiqada) kuzatadi; shu job
    (kunlik) endi faqat fasad_sex uchun ishlaydi."""
    async with async_session() as session:
        return await TaskRepository(session).list_open_orders_excluding_module(MEBEL)


async def _update_title_if_changed(task_id: int, new_title: str) -> bool:
    async with async_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        if task is None or task.title == new_title:
            return False
        await task_repo.update(task, title=new_title)
        await session.commit()
        return True


async def _update_label(task: Task) -> None:
    """6.3-band: hali ochiq (arxivlanmagan) karta uchun muddatga mos label
    qo'yadi. `TrelloLabelNotFoundError` (karta/board topilmadi) va boshqa
    kutilmagan xatolar bu yerda emas, chaqiruvchi tsiklda ushlanadi —
    shunda bitta vazifadagi label xatosi qolganlarni tekshirishni
    to'xtatmaydi."""
    # SPEC.md §6.2: to'xtatilgan vazifada muddat emas, HOLAT hal qiladi —
    # aks holda bu kunlik job "To'xtatilgan" labelini har kuni muddatga
    # asoslangan rangga almashtirib yuborardi (STOP belgisi bir kunda
    # yo'qolardi).
    status = (
        trello_sync_service.CardStatus.STOPPED
        if task.status == TaskStatus.STOPPED
        else trello_sync_service.determine_status(task.deadline)
    )
    await trello_sync_service.update_card_label(task.trello_card_id, status)


async def run(bot: Bot) -> None:
    """Scheduler shu funksiyani chaqiradi. Bitta kartadagi xatolik qolgan
    vazifalarni tekshirishni to'xtatmaydi — har biri alohida try/except ichida."""
    try:
        tasks = await _list_open_tasks()
    except Exception:
        logger.exception("daily_sync_job: ochiq vazifalar ro'yxatini olishda xatolik")
        return

    updated_titles = 0
    closed_tasks = 0
    relabeled = 0
    failed = 0

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for task in tasks:
            try:
                card = await trello.get_card(task.trello_card_id)
            except TrelloAPIError as exc:
                logger.warning(
                    "daily_sync_job: task %s (karta %s) o'qilmadi (status=%s)",
                    task.id, task.trello_card_id, exc.status,
                )
                failed += 1
                continue
            except Exception:
                logger.exception("daily_sync_job: task %s uchun Trello so'rovida kutilmagan xatolik", task.id)
                failed += 1
                continue

            try:
                new_title = card.get("name")
                if new_title and await _update_title_if_changed(task.id, new_title):
                    updated_titles += 1

                if card.get("closed"):
                    await penalty_service.finalize_task_and_apply_penalty(bot, task.id)
                    closed_tasks += 1
                else:
                    try:
                        await _update_label(task)
                        relabeled += 1
                    except trello_sync_service.TrelloLabelNotFoundError:
                        logger.warning(
                            "404 Label Not Found: task %s (karta %s) uchun label yangilanmadi",
                            task.id, task.trello_card_id,
                        )
                    except Exception:
                        logger.exception("daily_sync_job: label yangilashda xatolik (task_id=%s)", task.id)
            except Exception:
                logger.exception("daily_sync_job: task %s ni yangilashda xatolik", task.id)
                failed += 1

    logger.info(
        "daily_sync_job yakunlandi: %s nom yangilandi, %s vazifa yopildi, %s label yangilandi, "
        "%s xatolik (jami %s vazifa tekshirildi)",
        updated_titles, closed_tasks, relabeled, failed, len(tasks),
    )
