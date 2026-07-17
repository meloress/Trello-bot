"""Vaqtinchalik: 6-bosqich A-qismi, to'liq uchdan-uchga (E2E) smoke test.

Real Railway DB + Trello "Test" board'ga qarshi ishlaydi (hech qachon
"Fasad seh" production board emas). Butun ishlab chiqarish oqimini bir
martalik skriptda ketma-ket tekshiradi: buyurtma yaratish -> muddat
o'tganini aniqlash -> 8.3 avto-o'tkazish -> bosqich yakunlash -> kechikish
jarimasi -> keyingi bosqichga o'tish -> muddatidan oldin yakunlash -> plus
ball -> statistika -> davriy hisobot -> mijoz xabarnomasi.

CLAUDE.md konvensiyasi: ishlatilgach o'chiriladi (`rm bot/_smoke_e2e_full.py`).

Oldindan shart (Test board + Railway DB'da qo'lda tayyorlanishi kerak):
- Kamida ikkita bo'lim (departments) `next_department_id` orqali
  zanjirlangan, ikkalasida ham `trello_list_id` sozlangan.
- Birinchi bo'limda kamida bitta faol brigada (xodimlari bilan), ikkinchi
  bo'limda kamida bitta faol brigada (xodimlari bilan).
- Ixtiyoriy: kamida bitta faol ADMIN xodim (aks holda 11-qadam hech kimga
  yubormaydi, lekin xatosiz o'tishi kerak).

Ishga tushirish:
    cd bot && .venv\\Scripts\\python _smoke_e2e_full.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from config import settings
from core.database import async_session
from db.repositories import (
    BrigadeRepository,
    ClientRepository,
    DepartmentRepository,
    EmployeeRepository,
    KpiLogRepository,
    TaskAssignmentRepository,
    TaskRepository,
)
from jobs import overdue_watch_job, report_job
from services import client_service, notification_service, penalty_service, stats_service, task_service, timer_service
from utils.enums import Role

_TEST_PHONE = "+998900000099"


async def main() -> None:
    async with async_session() as session:
        departments = await DepartmentRepository(session).list_all()
    chain = next(
        (
            (d1, d2)
            for d1 in departments
            for d2 in departments
            if d1.next_department_id == d2.id and d1.trello_list_id and d2.trello_list_id
        ),
        None,
    )
    assert chain, "kamida ikkita zanjirlangan, Trello list sozlangan bo'lim kerak (Test board)"
    dept1, dept2 = chain

    async with async_session() as session:
        brigades1 = await BrigadeRepository(session).list_by_department(dept1.id)
        brigades2 = await BrigadeRepository(session).list_by_department(dept2.id)
        admins = await EmployeeRepository(session).list_by_role(Role.ADMIN)
    assert brigades1, f"'{dept1.name}' uchun faol brigada kerak"
    assert brigades2, f"'{dept2.name}' uchun faol brigada kerak"

    async with async_session() as session:
        workers1 = await EmployeeRepository(session).list_by_brigade(brigades1[0].id)
        workers2 = await EmployeeRepository(session).list_by_brigade(brigades2[0].id)
    assert workers1, f"'{brigades1[0].name}' brigadasida faol xodim kerak"
    assert workers2, f"'{brigades2[0].name}' brigadasida faol xodim kerak"

    bot = Bot(token=settings.bot_token)
    task = next_task = None

    try:
        client = await client_service.find_or_create_client(
            phone_number=_TEST_PHONE, full_name="E2E Smoke Client"
        )

        past_deadline = datetime.now(timezone.utc) - timedelta(hours=50)
        task = await task_service.create_task(
            title="E2E smoke buyurtma",
            description="Avtomatik 6-bosqich A-qism testi",
            deadline=past_deadline,
            department_id=dept1.id,
            employee_ids=[e.id for e in workers1],
            client_id=client.id,
        )
        print(f"1. Task yaratildi: #{task.id}, karta {task.trello_card_id}")

        await overdue_watch_job.run(bot)
        async with async_session() as session:
            refreshed = await TaskRepository(session).get_by_id(task.id)
        assert refreshed.status.value == "overdue", f"kutilgan OVERDUE, keldi {refreshed.status}"
        print("2. overdue_watch_job: OVERDUE holatiga o'tdi")

        reassign_target = brigades1[1] if len(brigades1) >= 2 else brigades1[0]
        task = await task_service.reassign_task_brigade(task.id, reassign_target.id)
        assert task.reassigned_at is not None
        print(f"3. 8.3 avto-o'tkazish: brigada '{reassign_target.name}'ga o'tkazildi")

        task = await timer_service.finish_task(task.id)
        kpi_logs_stage1 = await penalty_service.calculate_and_apply_task_penalty(task.id)
        print(f"4. 1-bosqich yakunlandi, {len(kpi_logs_stage1)} ta KPI yozuvi (kechikish jarimasi)")

        next_task = await task_service.advance_task_stage(task.id)
        assert next_task is not None and next_task.status.value == "pending_setup"
        print(f"5. advance_task_stage: 2-bosqich yaratildi (#{next_task.id}, PENDING_SETUP)")

        future_deadline = datetime.now(timezone.utc) + timedelta(hours=48)
        next_task = await task_service.activate_pending_stage(
            next_task.id, deadline=future_deadline, employee_ids=[e.id for e in workers2]
        )
        assert next_task.status.value == "active"
        print("6. activate_pending_stage: 2-bosqich faollashtirildi")

        next_task = await timer_service.finish_task(next_task.id)
        kpi_logs_stage2 = await penalty_service.calculate_and_apply_task_penalty(next_task.id)
        print(f"7. 2-bosqich muddatidan oldin yakunlandi, {len(kpi_logs_stage2)} ta KPI yozuvi (plus ball)")

        final = await task_service.advance_task_stage(next_task.id)
        print(f"8. keyingi advance_task_stage: {'buyurtma to`liq tugadi' if final is None else 'kutilmagan qo`shimcha bosqich yaratildi'}")

        await notification_service.notify_client_stage_advanced(bot, next_task.id)
        print("9. notify_client_stage_advanced chaqirildi (xatosiz o'tdi)")

        daily = await stats_service.get_daily_stats()
        monthly = await stats_service.get_monthly_stats()
        print(f"10. Statistika hisoblandi: {len(daily)} kunlik qator, {len(monthly)} oylik qator")

        await report_job.run_daily(bot)
        print(f"11. report_job.run_daily ishladi ({len(admins)} ta admin'ga yuborilishi kerak edi)")

        print("\nPhase 6-A E2E smoke test OK")
    finally:
        async with async_session() as session:
            kpi_repo = KpiLogRepository(session)
            task_ids = {t.id for t in (task, next_task) if t is not None}
            employee_ids = {e.id for e in workers1} | {e.id for e in workers2}
            for employee_id in employee_ids:
                for log in await kpi_repo.list_by_employee(employee_id):
                    if log.task_id in task_ids:
                        await kpi_repo.delete(log)

            assignment_repo = TaskAssignmentRepository(session)
            for t_id in task_ids:
                for a in await assignment_repo.list_by_task(t_id):
                    await assignment_repo.delete(a)

            task_repo = TaskRepository(session)
            # previous_task_id FK: bola qatorni ota qatoridan oldin o'chirish kerak.
            if next_task is not None:
                row = await task_repo.get_by_id(next_task.id)
                if row:
                    await task_repo.delete(row)
            if task is not None:
                row = await task_repo.get_by_id(task.id)
                if row:
                    await task_repo.delete(row)

            client_row = await ClientRepository(session).get_by_phone_number(_TEST_PHONE)
            if client_row:
                await ClientRepository(session).delete(client_row)

            await session.commit()

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
