"""Nazorat Trello: zakaz faqat Trello'da beriladi — kartaga a'zo qo'shilsa
ishchiga muddati bilan xabar, bo'limsiz nazoratchi + kuzatuvchiga umumiy xabar.

1. `jobs/nazorat_trello_watch_job.run` — birinchi yurish eski hodisalarni
   yubormaydi, keyingi yurish faqat yangi hodisani bir marta yuboradi.
2. `notification_service.notify_trello_card_assigned` — kim qanday matn oladi.

Bazasiz, Trello'siz: oddiy `python tests/test_nazorat_trello_watch.py`.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs import nazorat_trello_watch_job  # noqa: E402
from services import notification_service as ns  # noqa: E402
from utils.enums import Role  # noqa: E402

WORKER = SimpleNamespace(id=169, full_name="Muruvatullayev Abdulloh", telegram_id=1690, role=Role.WORKER,
                         department_id=75, trello_member_id="m-worker", is_active=True)
HABIBULLA = SimpleNamespace(id=95, full_name="Habibulla", telegram_id=950, role=Role.SUPERVISOR,
                            department_id=None, trello_member_id=None, is_active=True)
DEPT_SUPERVISOR = SimpleNamespace(id=96, full_name="Shpon nazoratchi", telegram_id=960, role=Role.SUPERVISOR,
                                  department_id=38, trello_member_id=None, is_active=True)
OBSERVER = SimpleNamespace(id=176, full_name="Bahrom", telegram_id=1760, role=Role.OBSERVER,
                           department_id=None, trello_member_id=None, is_active=True)
OTHER_WORKER = SimpleNamespace(id=170, full_name="Boshqa ishchi", telegram_id=1700, role=Role.WORKER,
                               department_id=75, trello_member_id="m-other", is_active=True)
SELLER = SimpleNamespace(id=173, full_name="Abdurahim Qodirov", telegram_id=1730, role=Role.SELLER,
                        department_id=None, trello_member_id="m-seller", is_active=True)
OTHER_SELLER = SimpleNamespace(id=172, full_name="Husniddin", telegram_id=1720, role=Role.SELLER,
                              department_id=None, trello_member_id="m-seller2", is_active=True)
PEOPLE = [WORKER, HABIBULLA, DEPT_SUPERVISOR, OBSERVER, OTHER_WORKER, SELLER, OTHER_SELLER]


class _FakeDepartmentRepo:
    def __init__(self, _session):
        pass

    async def get_by_id(self, department_id):
        return SimpleNamespace(id=75, name="Kroychi", module="fasad_sex") if department_id == 75 else None


class _FakeEmployeeRepo:
    def __init__(self, _session):
        pass

    async def get_by_trello_member_id(self, member_id):
        return next((p for p in PEOPLE if p.trello_member_id == member_id), None)

    async def get_by_id(self, employee_id):
        return next((p for p in PEOPLE if p.id == employee_id), None)

    async def list_by_role(self, role, *, active_only=True):
        return [p for p in PEOPLE if p.role == role]


class _FakeSession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text))


async def _notify_checks():
    saved = (ns.async_session, ns.EmployeeRepository, ns.DepartmentRepository)
    ns.async_session = lambda: _FakeSession()
    ns.EmployeeRepository = _FakeEmployeeRepo
    ns.DepartmentRepository = _FakeDepartmentRepo
    try:
        due = datetime.now(timezone.utc) + timedelta(days=3, hours=1)
        bot = _FakeBot()
        await ns.notify_trello_card_assigned(
            bot, trello_member_id="m-worker", member_name="Abdulloh", card_name="Zakaz 2601",
            list_name="Abdulloh kroy chizish 24", due=due,
        )
        by_chat = dict(bot.sent)
        assert set(by_chat) == {WORKER.telegram_id, HABIBULLA.telegram_id, OBSERVER.telegram_id}, by_chat
        assert by_chat[WORKER.telegram_id].startswith("🆕 Sizga yangi zakaz: «Zakaz 2601»")
        assert "(3 kun)" in by_chat[WORKER.telegram_id], "ishchi xabarida muddat yo'q"
        assert WORKER.full_name in by_chat[OBSERVER.telegram_id] and "Sizga" not in by_chat[OBSERVER.telegram_id]
        assert OTHER_WORKER.telegram_id not in by_chat, "boshqa ishchiga xabar ketdi"

        # Kartada sotuvchi bor, ishchi qo'shildi -> sotuvchiga "kroychiga berildi".
        bot = _FakeBot()
        await ns.notify_trello_card_assigned(
            bot, trello_member_id="m-worker", member_name=None, card_name="2521 Sarvar aka",
            list_name="Abdulloh kroy chizish 24", due=due, card_member_ids=["m-seller", "m-worker"],
        )
        by_chat = dict(bot.sent)
        assert by_chat[SELLER.telegram_id].startswith("📌 Zakazingiz kroychiga berildi: «2521 Sarvar aka»"), by_chat
        assert f"👷 Ijrochi: {WORKER.full_name}" in by_chat[SELLER.telegram_id]
        assert OTHER_SELLER.telegram_id not in by_chat, "kartada yo'q sotuvchiga xabar ketdi"
        assert by_chat[WORKER.telegram_id].startswith("🆕 Sizga yangi zakaz")

        # Sotuvchining o'zi qo'shildi -> unga sotuvchi matni, "Sizga yangi zakaz" emas.
        bot = _FakeBot()
        await ns.notify_trello_card_assigned(
            bot, trello_member_id="m-seller", member_name=None, card_name="2521 Sarvar aka",
            list_name=None, due=None, card_member_ids=["m-seller", "m-worker"],
        )
        by_chat = dict(bot.sent)
        assert by_chat[SELLER.telegram_id].startswith("💼 Siz zakazga sotuvchi sifatida biriktirildingiz"), by_chat
        assert WORKER.telegram_id not in by_chat, "sotuvchi qo'shilganda ishchiga xabar ketdi"
        assert "sotuvchi biriktirildi" in by_chat[OBSERVER.telegram_id]

        # Trello a'zosi xodimga bog'lanmagan — ishchiga hech kim yo'q, nazoratchilar baribir oladi.
        bot = _FakeBot()
        await ns.notify_trello_card_assigned(
            bot, trello_member_id="unknown", member_name="Trello Odam", card_name="Z", list_name=None, due=None,
        )
        by_chat = dict(bot.sent)
        assert set(by_chat) == {HABIBULLA.telegram_id, OBSERVER.telegram_id}, by_chat
        assert "Trello Odam" in by_chat[OBSERVER.telegram_id] and "belgilanmagan" in by_chat[OBSERVER.telegram_id]
    finally:
        ns.async_session, ns.EmployeeRepository, ns.DepartmentRepository = saved


async def _job_checks():
    """Job: birinchi yurish jim; keyin qo'shish/almashtirish/olib tashlash/
    muddat/arxiv hodisalari to'g'ri hold amallariga aylanadi."""
    from services import trello_hold_service as holds

    job = nazorat_trello_watch_job
    t0 = datetime(2026, 10, 24, 5, tzinfo=timezone.utc)
    iso = lambda dt: dt.isoformat().replace("+00:00", "Z")
    store = {"cursor": None, "holds": [], "next": 1, "log": []}
    people = {"m-a": (SimpleNamespace(id=1, department_id=75), holds.WORKER),
              "m-b": (SimpleNamespace(id=2, department_id=75), holds.WORKER),
              "m-s": (SimpleNamespace(id=3, department_id=None), holds.OTHER)}

    async def get_cursor():
        return store["cursor"]

    async def set_cursor(c):
        store["cursor"] = c

    async def open_holds(card_id):
        return list(store["holds"])

    async def open_hold(*, card_id, card_name, employee, started_at, deadline):
        store["holds"].append((store["next"], employee.id, started_at))
        store["log"].append(("open", employee.id, deadline))
        store["next"] += 1

    async def close_hold(bot, task_id, *, at, due, started_at):
        store["holds"] = [h for h in store["holds"] if h[0] != task_id]
        store["log"].append(("close", task_id, at - started_at))

    async def set_deadline(card_id, deadline):
        store["log"].append(("due", deadline))

    async def card_moved(bot, card_id, *, before, after, at, due):
        store["log"].append(("move", before, after))

    async def member(mid):
        return people.get(mid, (None, holds.UNKNOWN))

    async def notify(bot, **kw):
        store["log"].append(("notify", kw["trello_member_id"]))

    due = t0 + timedelta(days=3)

    class FakeTrello:
        def __init__(self, actions):
            self.actions = actions

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def _request(self, method, path, params=None):
            if path.endswith("/actions"):
                return self.actions[:1] if params.get("limit") == 1 else self.actions
            return {"name": "2630 Test", "due": iso(due), "idMembers": [], "list": {"name": "kroy"}}

    def act(kind, at, member_id=None, **data):
        d = {"card": {"id": "c1", **data.pop("card", {})}, **data}
        if member_id:
            d["idMember"] = member_id
        return {"id": f"{kind}{at}", "type": kind, "date": iso(at), "data": d}

    saved = (job.settings_service.get_trello_cursor, job.settings_service.set_trello_cursor, holds.open_holds,
             holds.open_hold, holds.close_hold, holds.set_card_deadline, holds.card_moved, job._member,
             job.notification_service.notify_trello_card_assigned, job._board_id)
    holds.card_moved = card_moved
    job.settings_service.get_trello_cursor, job.settings_service.set_trello_cursor = get_cursor, set_cursor
    holds.open_holds, holds.open_hold, holds.close_hold, holds.set_card_deadline = open_holds, open_hold, close_hold, set_deadline
    job._member, job.notification_service.notify_trello_card_assigned, job._board_id = member, notify, "board"
    try:
        old = act("addMemberToCard", t0 - timedelta(days=30), "m-a")
        assert await job.run(None, lambda: FakeTrello([old])) == 0 and store["log"] == [], "eski hodisa qayta ishlandi"
        assert store["cursor"] == old["date"]

        events = [
            act("addMemberToCard", t0, "m-a"),                                  # A boshladi
            act("addMemberToCard", t0 + timedelta(minutes=3), "m-s"),           # sotuvchi — ta'sirsiz
            act("addMemberToCard", t0 + timedelta(hours=80), "m-b"),            # B qo'shildi -> A yopiladi
            act("updateCard", t0 + timedelta(hours=81), card={"due": iso(due)}, old={"due": None}),
            act("removeMemberFromCard", t0 + timedelta(hours=90), "m-b"),       # B olib tashlandi
            act("addMemberToCard", t0 + timedelta(hours=91), "m-a"),
            act("updateCard", t0 + timedelta(hours=92), old={"idList": "l1"},
                listBefore={"name": "Abdulloh kroy chizish 24"}, listAfter={"name": "zakaz tushti stopda"}),
            act("updateCard", t0 + timedelta(hours=95), card={"closed": True}, old={"closed": False}),
        ]
        assert await job.run(None, lambda: FakeTrello(list(reversed(events)))) == len(events)
        kinds = [e for e in store["log"] if e[0] != "notify"]
        assert kinds == [
            ("open", 1, due),
            ("close", 1, timedelta(hours=80)), ("open", 2, due),
            ("due", due),
            ("close", 2, timedelta(hours=10)),
            ("open", 1, due),
            ("move", "Abdulloh kroy chizish 24", "zakaz tushti stopda"),
            ("close", 3, timedelta(hours=4)),
        ], kinds
        assert store["holds"] == [], "arxivdan keyin ochiq vaqt qoldi"
        assert "updateCard:idList" in job._FILTER, "list ko'chirish hodisasi o'qilmayapti"
        assert await job.run(None, lambda: FakeTrello(list(reversed(events)))) == 0, "hodisa ikki marta ishlandi"
    finally:
        (job.settings_service.get_trello_cursor, job.settings_service.set_trello_cursor, holds.open_holds,
         holds.open_hold, holds.close_hold, holds.set_card_deadline, holds.card_moved, job._member,
         job.notification_service.notify_trello_card_assigned, job._board_id) = saved


async def _close_checks():
    """close_hold: 10 daqiqadan kam, muddatsiz yoki muddati odamga berilishidan
    oldin o'tgan — ballsiz; aks holda eski tizim. card_moved: rejaga ko'ra
    pauza/davom/yopish chaqiriladi."""
    from services import trello_hold_service as holds

    calls = []

    async def finish(task_id, finished_at=None, employee_id=None):
        calls.append(("finish", task_id))

    async def finalize(bot, task_id, *, finished_at=None, employee_id=None):
        calls.append(("score", task_id))

    t0 = datetime(2026, 10, 24, 5, tzinfo=timezone.utc)

    async def store_deadline(task_id, due):
        return True, holds.effective_deadline(due, t0)

    async def resume(task_id, *, at):
        calls.append(("resume", task_id))

    async def pause(task_id, *, at):
        calls.append(("pause", task_id))

    async def open_holds(card_id):
        return [(7, 169, t0)]

    saved = (holds.timer_service.finish_task, holds.penalty_service.finalize_task_and_apply_penalty,
             holds._store_deadline, holds.resume_hold, holds.pause_hold, holds.open_holds,
             holds.async_session, holds.EmployeeRepository)
    holds.timer_service.finish_task = finish
    holds.penalty_service.finalize_task_and_apply_penalty = finalize
    (holds._store_deadline, holds.resume_hold, holds.pause_hold, holds.open_holds,
     holds.async_session, holds.EmployeeRepository) = (store_deadline, resume, pause, open_holds,
                                                       _FakeSession, _FakeEmployeeRepo)
    try:
        due = t0 + timedelta(days=3)
        await holds.close_hold(None, 1, at=t0 + timedelta(minutes=5), due=due, started_at=t0)
        await holds.close_hold(None, 2, at=t0 + timedelta(days=4), due=None, started_at=t0)
        await holds.close_hold(None, 3, at=t0 + timedelta(days=4), due=due, started_at=t0)
        await holds.close_hold(None, 4, at=t0 + timedelta(days=4), due=t0 - timedelta(days=2), started_at=t0)
        assert [c for c in calls if c[0] != "resume"] == [
            ("finish", 1), ("finish", 2), ("score", 3), ("finish", 4)], calls
        assert ("resume", 3) in calls, "pauzadagi hold yopilishdan oldin davom ettirilmadi"

        calls.clear()
        at = t0 + timedelta(hours=5)
        await holds.card_moved(None, "c1", before="Abdulloh kroy chizish 24", after="zakaz tushti stopda", at=at, due=due)
        await holds.card_moved(None, "c1", before="zakaz tushti stopda", after="Abdulloh kroy chizish 24", at=at, due=due)
        await holds.card_moved(None, "c1", before="Abdulloh jiyan chizish 24", after="Abdulloh kroy chizish 24", at=at, due=due)
        await holds.card_moved(None, "c1", before="Abdulloh kroy chizish 24", after="Fayl yeg'ish  va zapchast 24", at=at, due=due)
        assert calls == [("pause", 7), ("resume", 7), ("resume", 7), ("score", 7)], calls
    finally:
        (holds.timer_service.finish_task, holds.penalty_service.finalize_task_and_apply_penalty,
         holds._store_deadline, holds.resume_hold, holds.pause_hold, holds.open_holds,
         holds.async_session, holds.EmployeeRepository) = saved


def _no_bot_write_checks():
    """Trello zakazining muddati/srochnosti/ijrochisini botdan o'zgartiradigan
    endpointlar `is_trello_owned_order` bilan 409 qaytarishi kerak."""
    import inspect

    from miniapp.api import admin, brigadier

    for handler in (admin.update_task_deadline, admin.set_task_urgent, admin.activate_pending_stage,
                    admin.reassign_task, brigadier.delegate_task):
        assert "is_trello_owned_order(task_id)" in inspect.getsource(handler), handler.__name__


async def main():
    from services import trello_hold_service

    trello_hold_service.demo()
    _no_bot_write_checks()
    await _job_checks()
    await _close_checks()
    await _notify_checks()
    print("test_nazorat_trello_watch: OK")


if __name__ == "__main__":
    asyncio.run(main())
