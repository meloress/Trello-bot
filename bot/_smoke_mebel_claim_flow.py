"""Vaqtinchalik: mebel bir-tomonlama-sync (Trello -> bot) uchdan-uchga (E2E)
smoke test — claim-tasdiqlash oqimi (`.claude/plans/mebel-ishlab-chiqarish-
bo-limida-vast-kahn.md`, 11-vazifa).

Real Railway DB + FAQAT shu skript uchun yaratiladigan YANGI Trello board'ga
qarshi ishlaydi (hech qachon "Test"/"Fasad seh" production board emas — bu
skript karta yaratadi/ko'chiradi, shuning uchun alohida, bir martalik board
shart, CLAUDE.md Gotchas bo'limiga qarang).

Tekshiradi:
1. Trello kartadan yangi buyurtma avtomatik yaratilishi (`trello_ingest_job.run`
   + `task_service.sync_trello_card_stage`).
2. Ishchi "Yakunlash" bosganda claim PENDING holatida yaratilib, vazifaning
   o'ziga HALI tegmasligi.
3. Rahbar tasdiqlaganda `finished_at` sifatida rahbar TASDIQLAGAN vaqt emas,
   ishchi TUGMANI BOSGAN aniq vaqt (`claim.claimed_at`) ishlatilishi — shu
   skriptdagi ENG MUHIM tekshiruv.
4. Rad etish hech qanday task mutatsiyasiga sabab bo'lmasligi.
5. Karta qo'lda keyingi bo'lim list'iga ko'chirilganda, navbatdagi ingest
   pollida yangi bosqich qatori avtomatik yaratilishi.

CLAUDE.md konvensiyasi: `_smoke_*` skriptlar ishlatilgach o'chiriladi.

Oldindan shart (Railway DB'da qo'lda tayyorlanishi kerak — bu skript yangi
xodim YARATMAYDI, chunki xodimga haqiqiy Trello `trello_member_id` berish
uchun haqiqiy Trello a'zoligi kerak, buni skript o'zi taxmin qila olmaydi):
- Kamida bitta faol xodim, `trello_member_id` ustuni to'ldirilgan (istalgan
  bo'lim/rol — shu xodim test kartalarining a'zosi sifatida ishlatiladi).
- Kamida bitta faol ADMIN xodim (claim'larni tasdiqlash/rad etish uchun —
  ADMIN doim `claim_service._reviewer_in_scope()` doirasida, bo'lim
  cheklovisiz).

Ishga tushirish:
    cd bot && .venv\\Scripts\\python _smoke_mebel_claim_flow.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from config import settings
from core.database import async_session
from db.repositories import (
    DepartmentRepository,
    EmployeeRepository,
    TaskAssignmentRepository,
    TaskClaimRepository,
    TaskRepository,
)
from jobs import trello_ingest_job
from services import claim_service
from trello.client import TrelloClient
from utils.enums import ClaimActionType, ClaimStatus, Role, TaskStatus

_BOARD_NAME = "Mebel claim-flow smoke test"


async def main() -> None:
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        all_employees = await employee_repo.list_active()
        admins = await employee_repo.list_by_role(Role.ADMIN)

    member_employee = next((e for e in all_employees if e.trello_member_id), None)
    assert member_employee is not None, (
        "kamida bitta faol xodim trello_member_id bilan sozlangan bo'lishi kerak "
        "(haqiqiy Trello a'zosi — bu skript o'zi bunday xodim yarata olmaydi)"
    )
    assert admins, "kamida bitta faol ADMIN xodim kerak (claim'larni tasdiqlash/rad etish uchun)"
    reviewer = admins[0]

    bot = Bot(token=settings.bot_token)

    dept1_id = dept2_id = None
    task1 = task2_rejected = task3_next_stage = None
    claim1 = claim2 = None

    try:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            board = await trello.create_board(_BOARD_NAME)
            list1 = await trello.create_list(board["id"], "1-bosqich")
            list2 = await trello.create_list(board["id"], "2-bosqich")
        print(f"1. Trello board yaratildi: {board['name']} ({board['id']}), 2 ta list")

        async with async_session() as session:
            department_repo = DepartmentRepository(session)
            dept1 = await department_repo.create(
                name="Smoke test 1-bosqich", trello_list_id=list1["id"], module="mebel"
            )
            dept2 = await department_repo.create(
                name="Smoke test 2-bosqich", trello_list_id=list2["id"], module="mebel"
            )
            await session.flush()
            await department_repo.update(dept1, next_department_id=dept2.id)
            await session.commit()
            dept1_id, dept2_id = dept1.id, dept2.id
        print(f"2. Vaqtinchalik mebel bo'limlari: #{dept1_id} -> #{dept2_id}")

        # 3. Yangi buyurtma: Trello kartadan avtomatik yaratilish.
        due1 = datetime.now(timezone.utc) + timedelta(days=2)
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            card1 = await trello.create_card(list1["id"], "Smoke test buyurtma #1", due=due1)
            await trello.add_member_to_card(card1["id"], member_employee.trello_member_id)

        await trello_ingest_job.run(bot)

        async with async_session() as session:
            task1 = await TaskRepository(session).get_by_trello_card_id(card1["id"])
        assert task1 is not None, "trello_ingest_job kartadan yangi vazifa yaratmadi"
        assert task1.status == TaskStatus.ACTIVE, f"kutilgan ACTIVE, keldi {task1.status}"
        assert task1.trello_last_seen_member_ids, "trello_last_seen_member_ids to'ldirilmagan"

        async with async_session() as session:
            assignments = await TaskAssignmentRepository(session).list_by_task(task1.id)
        assert {a.employee_id for a in assignments} == {member_employee.id}, (
            f"kutilgan tayinlanish {member_employee.id}, keldi {[a.employee_id for a in assignments]}"
        )
        print(f"3. Trello kartadan yangi buyurtma: task #{task1.id}, ACTIVE, xodim #{member_employee.id}ga tayinlangan")

        # 4. "Yakunlash" claim yuboriladi — vazifaning o'ziga hali tegmaydi.
        claimed_at_1 = datetime.now(timezone.utc) - timedelta(hours=3)
        claim1 = await claim_service.submit_claim(
            task1.id, member_employee.id, ClaimActionType.FINISH, claimed_at=claimed_at_1
        )
        assert claim1.status == ClaimStatus.PENDING
        async with async_session() as session:
            refreshed1 = await TaskRepository(session).get_by_id(task1.id)
        assert refreshed1.status == TaskStatus.ACTIVE, "claim yuborilishi vazifani ACTIVE holatidan chiqarmasligi kerak"
        assert refreshed1.finished_at is None, "claim yuborilishi finished_at'ni hali belgilamasligi kerak"
        print(f"4. Yakunlash claim'i yuborildi (#{claim1.id}, PENDING), vazifa hali ACTIVE")

        # 5. Tasdiqlash: finished_at = claim.claimed_at (rahbar tasdiqlagan vaqt EMAS).
        approved1 = await claim_service.approve_claim(claim1.id, reviewer.id)
        assert approved1.status == ClaimStatus.APPROVED
        async with async_session() as session:
            task1 = await TaskRepository(session).get_by_id(task1.id)
        assert task1.status == TaskStatus.COMPLETED, f"kutilgan COMPLETED, keldi {task1.status}"
        print(f"5. Tasdiqlandi: task1.finished_at={task1.finished_at!r}, claim.claimed_at={claimed_at_1!r}")
        assert task1.finished_at == claimed_at_1, (
            f"finished_at ISHCHI bosgan vaqt bo'lishi kerak edi ({claimed_at_1}), "
            f"lekin {task1.finished_at} keldi (ehtimol tasdiqlash vaqti ishlatilgan)"
        )

        # 6. Rad etish: hech qanday task mutatsiyasi bo'lmaydi.
        due2 = datetime.now(timezone.utc) + timedelta(days=2)
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            card2 = await trello.create_card(list1["id"], "Smoke test buyurtma #2", due=due2)
            await trello.add_member_to_card(card2["id"], member_employee.trello_member_id)

        await trello_ingest_job.run(bot)
        async with async_session() as session:
            task2_rejected = await TaskRepository(session).get_by_trello_card_id(card2["id"])
        assert task2_rejected is not None and task2_rejected.status == TaskStatus.ACTIVE
        print(f"6. Ikkinchi test buyurtmasi: task #{task2_rejected.id}, ACTIVE")

        claimed_at_2 = datetime.now(timezone.utc) - timedelta(hours=1)
        claim2 = await claim_service.submit_claim(
            task2_rejected.id, member_employee.id, ClaimActionType.FINISH, claimed_at=claimed_at_2
        )
        rejected2 = await claim_service.reject_claim(claim2.id, reviewer.id, note="test rejection")
        assert rejected2.status == ClaimStatus.REJECTED
        async with async_session() as session:
            task2_rejected = await TaskRepository(session).get_by_id(task2_rejected.id)
        assert task2_rejected.status == TaskStatus.ACTIVE, "rad etish vazifa holatini o'zgartirmasligi kerak"
        assert task2_rejected.finished_at is None, "rad etish finished_at'ni belgilamasligi kerak"
        print(f"7. Rad etildi (#{claim2.id}): vazifa hali ACTIVE, finished_at hali None")

        # 8. Bosqich o'tishi: karta qo'lda keyingi list'ga ko'chiriladi.
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card1["id"], list2["id"])

        await trello_ingest_job.run(bot)
        async with async_session() as session:
            task3_next_stage = await TaskRepository(session).get_latest_by_trello_card_id(card1["id"])
        assert task3_next_stage is not None and task3_next_stage.id != task1.id, (
            "karta ko'chirilgandan keyin yangi bosqich qatori yaratilmadi"
        )
        assert task3_next_stage.previous_task_id == task1.id
        assert task3_next_stage.current_department_id == dept2_id
        assert task3_next_stage.status == TaskStatus.ACTIVE
        print(
            f"8. Bosqich o'tishi: yangi task #{task3_next_stage.id} "
            f"(previous_task_id={task3_next_stage.previous_task_id}, bo'lim=#{dept2_id}, ACTIVE)"
        )

        print("\nMebel claim-flow smoke test OK")
    finally:
        async with async_session() as session:
            claim_repo = TaskClaimRepository(session)
            for claim in (claim1, claim2):
                if claim is not None:
                    row = await claim_repo.get_by_id(claim.id)
                    if row is not None:
                        await claim_repo.delete(row)

            assignment_repo = TaskAssignmentRepository(session)
            task_ids = {t.id for t in (task1, task2_rejected, task3_next_stage) if t is not None}
            for t_id in task_ids:
                for a in await assignment_repo.list_by_task(t_id):
                    await assignment_repo.delete(a)

            task_repo = TaskRepository(session)
            # previous_task_id FK: bola qatorni ota qatoridan oldin o'chirish kerak.
            if task3_next_stage is not None:
                row = await task_repo.get_by_id(task3_next_stage.id)
                if row is not None:
                    await task_repo.delete(row)
            if task1 is not None:
                row = await task_repo.get_by_id(task1.id)
                if row is not None:
                    await task_repo.delete(row)
            if task2_rejected is not None:
                row = await task_repo.get_by_id(task2_rejected.id)
                if row is not None:
                    await task_repo.delete(row)

            department_repo = DepartmentRepository(session)
            # next_department_id FK: dept1 -> dept2, shuning uchun dept1
            # (FK'ni USHLAB turgan qator) dept2'dan oldin o'chiriladi.
            if dept1_id is not None:
                row = await department_repo.get_by_id(dept1_id)
                if row is not None:
                    await department_repo.delete(row)
            if dept2_id is not None:
                row = await department_repo.get_by_id(dept2_id)
                if row is not None:
                    await department_repo.delete(row)

            await session.commit()

        await bot.session.close()

        print(
            f"\nESLATMA: Trello'dagi vaqtinchalik board ('{_BOARD_NAME}') qo'lda "
            "arxivlanishi/o'chirilishi kerak — TrelloClient'da board o'chirish metodi "
            "yo'q (qasddan, bu vazifa doirasidan tashqari)."
        )


if __name__ == "__main__":
    asyncio.run(main())
