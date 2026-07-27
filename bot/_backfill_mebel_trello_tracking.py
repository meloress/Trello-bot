"""Vaqtinchalik: mebel bir-tomonlama-sync joriy etishdan OLDIN ishga
tushiriladigan moslashtirish skripti (rollout xavfsizligi,
`.claude/plans/mebel-ishlab-chiqarish-bo-limida-vast-kahn.md` 8-bo'lim).

`jobs/trello_ingest_job.py` (har 5 daqiqada, HECH QANDAY feature-flag'siz
`main.py`da ro'yxatdan o'tkazilgan) birinchi marta ishga tushganda, hozir
ochiq turgan mebel ORDER vazifalarining `trello_last_seen_list_id`/
`trello_last_seen_member_ids` ustunlari hali NULL — bu ularni "o'zgargan"
deb noto'g'ri aniqlab, kutilmagan qayta-tayinlash/moslashtirish signalini
ishga tushirib qo'yishi mumkin. Bu skript shu ustunlarni Trello kartaning
HOZIRGI holatidan oldindan to'ldiradi.

MUHIM DEPLOY TARTIBI: bu skriptni ishga tushirmasdan turib
`trello_ingest_job` ro'yxatdan o'tkazilgan versiyani deploy qilmang — yoki
deploy allaqachon bo'lgan bo'lsa, birinchi 5 daqiqalik tikdan OLDIN shu
skriptni yakunlang.

Real Railway Postgres + real Trello (production) ustida ishlaydi — bu
skriptning o'zi Trello'ga HECH NARSA yozmaydi (faqat `list_cards_in_list`
orqali o'qiydi), lekin bazaga yozadi. Ishlatilgach o'chirilmaydi (bir
martalik `_smoke_*` skriptlaridan farqli) — qayta ishga tushirish xavfsiz
(idempotent: mavjud qiymatlarni Trello'ning haqiqiy joriy holati bilan
almashtiradi), kelajakda yana kerak bo'lishi mumkin (masalan yangi mebel
bo'limi qo'shilganda).

Ishga tushirish:
    cd bot && .venv\\Scripts\\python _backfill_mebel_trello_tracking.py
"""

import asyncio

from config import settings
from core.database import async_session
from db.repositories import DepartmentRepository, TaskRepository
from trello.client import TrelloAPIError, TrelloClient
from utils.enums import TaskStatus, TaskType

_OPEN_STATUSES = (TaskStatus.ACTIVE, TaskStatus.STOPPED, TaskStatus.OVERDUE)


async def main() -> None:
    async with async_session() as session:
        departments = await DepartmentRepository(session).list_by_module("mebel")
    departments = [d for d in departments if d.trello_list_id]
    if not departments:
        print("Hech qanday mebel bo'limi trello_list_id bilan sozlanmagan — hech narsa qilinmadi.")
        return
    department_ids = {d.id for d in departments}

    async with async_session() as session:
        all_tasks = await TaskRepository(session).list_all()

    open_mebel_tasks = [
        t for t in all_tasks
        if t.task_type == TaskType.ORDER
        and t.status in _OPEN_STATUSES
        and t.trello_card_id
        and t.current_department_id in department_ids
    ]
    pending_setup_tasks = [
        t for t in all_tasks
        if t.task_type == TaskType.ORDER
        and t.status == TaskStatus.PENDING_SETUP
        and t.current_department_id in department_ids
    ]

    if pending_setup_tasks:
        print(
            f"OGOHLANTIRISH: {len(pending_setup_tasks)} ta mebel PENDING_SETUP vazifa topildi — "
            "trello_ingest_job yoqilishidan oldin bularni qo'lda hal qiling (Mini App'ning "
            "\"Sozlash kutilmoqda\" bo'limi / activate_pending_stage orqali), aks holda ingest "
            "job xuddi shu karta uchun dublikat qator yaratib qo'yishi mumkin:"
        )
        for task in pending_setup_tasks:
            print(f"  - task_id={task.id} title={task.title!r} trello_card_id={task.trello_card_id}")

    cards_by_id: dict[str, dict] = {}
    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for department in departments:
            try:
                cards = await trello.list_cards_in_list(department.trello_list_id)
            except TrelloAPIError as exc:
                print(f"Bo'lim {department.id} ({department.name}) kartalari o'qilmadi (status={exc.status})")
                continue
            for card in cards:
                cards_by_id[card["id"]] = card

    seeded = 0
    skipped = 0
    for task in open_mebel_tasks:
        card = cards_by_id.get(task.trello_card_id)
        if card is None:
            print(f"  task_id={task.id}: kartasi ({task.trello_card_id}) Trello'da topilmadi — o'tkazib yuborildi")
            skipped += 1
            continue
        async with async_session() as session:
            task_repo = TaskRepository(session)
            fresh = await task_repo.get_by_id(task.id)
            if fresh is None:
                continue
            await task_repo.update(
                fresh,
                trello_last_seen_list_id=card.get("idList"),
                trello_last_seen_member_ids=card.get("idMembers") or [],
            )
            await session.commit()
        seeded += 1

    print(f"Tayyor: {seeded} ta vazifa moslashtirildi, {skipped} ta o'tkazib yuborildi.")


if __name__ == "__main__":
    asyncio.run(main())
