"""Bir martalik (2026-11-04): list-ko'chirish qoidasi deploy bo'lishidan OLDIN
ochilgan Nazorat Trello holdlarini tuzatadi.

1. Har bir ochiq hold uchun kartaning Trello tarixidagi list ko'chirishlarini
   (hold boshlangandan keyin, job kursorigacha — undan keyingisini job o'zi
   qiladi) qayta o'ynaydi: pauza / davom / yopish (`plan_list_move`).
2. Ochiq qolganlarning muddatini kartaning hozirgi muddatidan qayta
   hisoblaydi — odamga berilishidan oldin o'tib ketgan muddat olib tashlanadi.

    .venv/Scripts/python _backfill_trello_holds.py          # faqat ko'rsatadi
    .venv/Scripts/python _backfill_trello_holds.py --apply  # bajaradi (ball xabarlari ketadi)
"""

import asyncio
import sys
from datetime import datetime

from aiogram import Bot
from sqlalchemy import select

from config import settings
from core.database import async_session
from db.models.department import Department
from db.models.task import Task
from db.repositories import EmployeeRepository, TaskAssignmentRepository
from services import settings_service, trello_hold_service as holds
from trello.client import TrelloClient
from utils.enums import TaskStatus, TaskType
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


async def main():
    cursor = await settings_service.get_trello_cursor()
    bot = Bot(settings.bot_token) if APPLY else None
    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for task, full_name in await _open_holds():
            card = await trello._request("GET", f"/cards/{task.trello_card_id}", params={"fields": "due,closed"})
            due = _dt(card.get("due"))
            moves = await trello._request(
                "GET", f"/cards/{task.trello_card_id}/actions",
                params={"filter": "updateCard:idList", "since": task.started_at.isoformat(), "limit": 1000},
            )
            moves = sorted((m for m in moves if m["date"] <= cursor), key=lambda m: m["date"])
            print(f"\n#{task.id} {task.title[:45]!r} — {full_name}, boshlangan {task.started_at:%d.%m %H:%M}, "
                  f"karta muddati {due:%d.%m %H:%M}" if due else f"\n#{task.id} {task.title[:45]!r} — {full_name}, muddatsiz")
            closed = False
            stopped, paused_at = task.stopped_seconds_total or 0, None  # ko'rsatish rejimi uchun pauza hisobi
            for m in moves:
                before, after = m["data"]["listBefore"]["name"], m["data"]["listAfter"]["name"]
                at = _dt(m["date"])
                action = holds.plan_list_move(before, after, [(task.id, full_name)])[task.id]
                print(f"   {at:%d.%m %H:%M}  {before!r} -> {after!r}: {action}")
                if not APPLY:
                    if action == holds.PAUSE:
                        paused_at = at
                    elif action in (holds.RESUME, holds.CLOSE) and paused_at:
                        stopped, paused_at = stopped + int((at - paused_at).total_seconds()), None
                    closed = action == holds.CLOSE
                    if closed:
                        deadline = holds.effective_deadline(due, task.started_at, stopped)
                        hours = (at - deadline).total_seconds() / 3600 if deadline else None
                        print("      -> " + ("ballsiz (muddat yo'q yoki odamga berilganda o'tib ketgan)" if hours is None
                                             else f"{abs(hours):.0f} soat {'kech' if hours > 0 else 'erta'}"))
                        break
                    continue
                if action == holds.PAUSE:
                    await holds.pause_hold(task.id, at=at)
                elif action == holds.RESUME:
                    await holds.resume_hold(task.id, at=at)
                elif action == holds.CLOSE:
                    await holds.close_hold(bot, task.id, at=at, due=due, started_at=task.started_at)
                    closed = True
                    break
            if not closed:
                new = holds.effective_deadline(due, task.started_at, task.stopped_seconds_total)
                if new != task.deadline:
                    print(f"   ochiq qoladi; muddat {task.deadline} -> {new}")
                    if APPLY:
                        await holds.set_card_deadline(task.trello_card_id, due)
                else:
                    print("   ochiq qoladi, o'zgarish yo'q")
    if bot:
        await bot.session.close()
    print("\nBAJARILDI" if APPLY else "\n(faqat ko'rsatildi — bajarish uchun --apply)")


if __name__ == "__main__":
    asyncio.run(main())
