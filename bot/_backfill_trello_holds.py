"""Bir martalik (2026-11-04): list-ko'chirish qoidasi deploy bo'lishidan OLDIN
ochilgan Nazorat Trello holdlarini tuzatadi.

1. Har bir ochiq hold uchun kartaning Trello tarixidagi list ko'chirishlarini
   (hold boshlangandan keyin, job kursorigacha — undan keyingisini job o'zi
   qiladi) qayta o'ynaydi: pauza / davom / yopish (`plan_list_move`).
2. Muddat kartaning Trello'dagi muddat TARIXIDAN tiklanadi — bot bilan bir xil
   `closing_deadline` qoidasi (o'tgan sanaga surilgan muddat o'rniga odamga
   berilgan paytdagi muddat — #202 dagi qaror).
3. Ochiq qolganlarning muddati shu qoida bilan to'g'rilanadi.

    .venv/Scripts/python _backfill_trello_holds.py          # faqat ko'rsatadi
    .venv/Scripts/python _backfill_trello_holds.py --apply  # bajaradi (ball xabarlari ketadi)

ponytail: pauza davrida muddat o'zgarishi hisobga olinmaydi (tuzatiladigan
kartalarning hech biri stopda bo'lmagan — 2026-11-04 da tekshirildi).
"""

import asyncio
import math
import sys
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select

from config import settings
from core.database import async_session
from db.models.department import Department
from db.models.task import Task
from db.repositories import EmployeeRepository, PenaltyRuleRepository, TaskAssignmentRepository, TaskRepository
from services import penalty_service, settings_service, trello_hold_service as holds
from trello.client import TrelloClient
from utils.enums import TaskStatus, TaskType
from utils.formatters import fmt_ball
from utils.modules import NAZORAT_TRELLO

APPLY = "--apply" in sys.argv


def _dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


async def _open_holds():
    async with async_session() as session:
        tasks = (await session.execute(
            select(Task).join(Department, Task.current_department_id == Department.id).where(
                Department.module == NAZORAT_TRELLO, Task.task_type == TaskType.ORDER,
                Task.trello_card_id.isnot(None), Task.status != TaskStatus.COMPLETED,
            ).order_by(Task.id)
        )).scalars().all()
        rows = []
        for task in tasks:
            assignment = (await TaskAssignmentRepository(session).list_by_task(task.id))[0]
            employee = await EmployeeRepository(session).get_by_id(assignment.employee_id)
            rows.append((task, employee.full_name))
    return rows


async def _set_deadline(task_id: int, deadline) -> None:
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        status = TaskStatus.OVERDUE if deadline is not None and deadline <= now else TaskStatus.ACTIVE
        if task.status == TaskStatus.STOPPED:
            status = TaskStatus.STOPPED
        await repo.update(task, deadline=deadline, status=status,
                          day_left_notified_at=None, last_overdue_reminder_at=None)
        await session.commit()


async def _preview_ball(task, deadline, at) -> str:
    if deadline is None:
        return "ballsiz (muddat yo'q)"
    seconds = (at - deadline).total_seconds()
    if seconds > 0:
        hours = math.ceil(seconds / 3600)
        async with async_session() as session:
            rules = await PenaltyRuleRepository(session).list_for_department(task.current_department_id)
        return f"{hours} soat kech -> {fmt_ball(penalty_service.hourly_penalty(rules, hours))} ball"
    hours = int(-seconds // 3600)
    plus = await penalty_service.calculate_plus_ball(hours)
    return f"{hours} soat erta -> {fmt_ball(plus) if plus else '0'} ball"


async def main():
    cursor = await settings_service.get_trello_cursor()
    ambiguous = holds.ambiguous_tokens((await holds._staff_names()).values())
    bot = Bot(settings.bot_token) if APPLY else None
    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for task, full_name in await _open_holds():
            card_id, started = task.trello_card_id, task.started_at
            card = await trello._request("GET", f"/cards/{card_id}", params={"fields": "due,closed"})
            due_now = _dt(card.get("due"))
            changes = sorted(
                (_dt(a["date"]), _dt(a["data"]["old"].get("due")))
                for a in await trello._request("GET", f"/cards/{card_id}/actions", params={"filter": "updateCard:due", "limit": 1000})
            )

            def due_at(moment):
                return holds.due_at(moment, changes, due_now)

            moves = await trello._request(
                "GET", f"/cards/{card_id}/actions",
                params={"filter": "updateCard:idList", "since": started.isoformat(), "limit": 1000},
            )
            moves = sorted((m for m in moves if m["date"] <= cursor), key=lambda m: m["date"])
            given = due_at(started)
            print(f"\n#{task.id} {task.title[:45]!r} — {full_name}, berilgan {started:%d.%m %H:%M}, "
                  f"o'shandagi muddat {given:%d.%m %H:%M}" if given else
                  f"\n#{task.id} {task.title[:45]!r} — {full_name}, berilganda muddatsiz")

            closed = False
            for m in moves:
                before, after = m["data"]["listBefore"]["name"], m["data"]["listAfter"]["name"]
                at = _dt(m["date"])
                action = holds.plan_list_move(before, after, [(task.id, full_name)], ambiguous)[task.id]
                print(f"   {at:%d.%m %H:%M}  {before!r} -> {after!r}: {action}")
                if action == holds.CLOSE:
                    deadline = holds.closing_deadline(due_at(at), given, started, task.stopped_seconds_total)
                    if at - started < holds.HOLD_GRACE:
                        print("      -> ballsiz (10 daqiqadan kam)")
                    else:
                        print("      -> " + await _preview_ball(task, deadline, at))
                    if APPLY:
                        await holds.close_hold(bot, task.id, at=at, due=due_at(at), started_at=started, given_due=given)
                    closed = True
                    break
                if APPLY and action == holds.PAUSE:
                    await holds.pause_hold(task.id, at=at)
                elif APPLY and action == holds.RESUME:
                    await holds.resume_hold(task.id, at=at)

            if not closed:
                new = holds.closing_deadline(due_now, given, started, task.stopped_seconds_total)
                if new != task.deadline:
                    print(f"   ochiq qoladi; muddat {task.deadline} -> {new}")
                    if APPLY:
                        await _set_deadline(task.id, new)
                else:
                    print("   ochiq qoladi, o'zgarish yo'q")
    if bot:
        await bot.session.close()
    print("\nBAJARILDI" if APPLY else "\n(faqat ko'rsatildi — bajarish uchun --apply)")


if __name__ == "__main__":
    asyncio.run(main())
