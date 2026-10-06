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
PEOPLE = [WORKER, HABIBULLA, DEPT_SUPERVISOR, OBSERVER, OTHER_WORKER]


class _FakeEmployeeRepo:
    def __init__(self, _session):
        pass

    async def get_by_trello_member_id(self, member_id):
        return next((p for p in PEOPLE if p.trello_member_id == member_id), None)

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
    saved = (ns.async_session, ns.EmployeeRepository)
    ns.async_session = lambda: _FakeSession()
    ns.EmployeeRepository = _FakeEmployeeRepo
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

        # Trello a'zosi xodimga bog'lanmagan — ishchiga hech kim yo'q, nazoratchilar baribir oladi.
        bot = _FakeBot()
        await ns.notify_trello_card_assigned(
            bot, trello_member_id="unknown", member_name="Trello Odam", card_name="Z", list_name=None, due=None,
        )
        by_chat = dict(bot.sent)
        assert set(by_chat) == {HABIBULLA.telegram_id, OBSERVER.telegram_id}, by_chat
        assert "Trello Odam" in by_chat[OBSERVER.telegram_id] and "belgilanmagan" in by_chat[OBSERVER.telegram_id]
    finally:
        ns.async_session, ns.EmployeeRepository = saved


async def main():
    await nazorat_trello_watch_job._demo()
    await _notify_checks()
    print("test_nazorat_trello_watch: OK")


if __name__ == "__main__":
    asyncio.run(main())
