# 5-bosqich: Sotuv CRM (Ezza + Melores) — Implementation Plan

> **For agentic workers:** This repo has no automated test suite (see CLAUDE.md).
> Each task's "Test" step is a one-off `bot/_smoke_phase5_sales.py` script run
> against the real Railway DB + a dedicated Trello "Test" board, per repo
> convention — not pytest. Execute task-by-task, inline, in one session.

**Goal:** Build the sales-CRM domain (leads -> funnel stages -> won/lost) for
the Ezza and Melores sales departments, fully separate from the production
task/KPI domain, per `.claude/plans/05-sotuv-crm.md`.

**Architecture:** New `leads` + `call_logs` tables (own domain, no touch to
`tasks`/`penalty_service`). Trello list ids per (brand, stage) live in a new
JSON column on the existing `app_settings` singleton (`sales_board_lists`),
configured directly in the DB — mirrors the existing precedent that
`departments.trello_list_id` also has no bot UI. Manual call-log entry only
(IP-telephony deferred — no provider chosen, confirmed with user). Follow-up
threshold is a plain configurable int on `app_settings`, wired into the
existing generic `/settings` field-editor (zero new UI code for that part).

**Tech Stack:** aiogram v3 (existing), SQLAlchemy 2.0 + Alembic, existing
`TrelloClient` (`trello/client.py`, no changes needed — `create_card`,
`move_card_to_list` already cover everything sales needs).

## Decisions locked in with the user before this plan was written

1. Leads live in a **new `leads` table**, not `tasks.task_type=LEAD` (avoids
   dragging deadline/KPI-shaped columns into a domain that has none of that).
2. Call logs are **manual entry only** (Telegram text or voice message).
   IP-telephony integration is explicitly deferred — no provider was named,
   and building a webhook receiver with no provider to test against would be
   dead code. `call_logs` schema is a plain log table, not provider-shaped.
3. `lead_follow_up_threshold_days` default is **7**, admin-editable via the
   existing `/settings` command (same mechanism as `financial_flag_threshold_days`).

## Global Constraints

- Layering: `handlers/` -> `services/` -> `db/repositories/` -> `db/models/`, one-way.
- Every new NOT NULL column on a non-empty table needs `server_default` (CLAUDE.md gotcha).
- Explicit FK names: `fk_<table>_<column>` (CLAUDE.md gotcha, autogenerate omits them).
- Enums: `native_enum=False`, `values_callable=lambda e: [m.value for m in e]` (existing convention in `task.py`/`employee.py`).
- Trello writes happen **before** the DB commit that depends on them succeeding (same rule as `task_service.create_task`).
- Secondary effects (Telegram notifications) are `try/except` + `logger.exception`, never allowed to make the primary action look like it failed.
- Never touch the real "Ezza sotuv" / "Melores Mebel sotuv" production boards during verification — only a dedicated Trello "Test" board (same rule as "Fasad seh").

---

### Task 1: Enums + `AppSetting` fields (brand/stage vocabulary, follow-up threshold, board-list config)

**Files:**
- Modify: `bot/utils/enums.py`
- Modify: `bot/db/models/app_setting.py`
- Modify: `bot/services/settings_service.py`
- Modify: `bot/keyboards/admin_kb.py` (SETTING_FIELD_LABELS only)
- Modify: `bot/handlers/admin/settings.py` (_PROMPTS + _parse_value only)
- Create: `bot/db/migrations/versions/<rev>_phase5_sales_settings.py`

**Interfaces:**
- Produces: `LeadBrand` (EZZA/MELORES), `LeadStage` (NEW_LEAD/CONTACTED/OFFER_SENT/AGREED/CLOSED_WON/CLOSED_LOST) enums.
- Produces: `AppSettingsSnapshot.lead_follow_up_threshold_days: int`, `AppSettingsSnapshot.sales_board_lists: dict`.

- [ ] **Step 1: Add enums**

In `bot/utils/enums.py`, append:

```python
class LeadBrand(str, Enum):
    """6.1-band: ikkita mustaqil sotuv yo'nalishi — har biri o'z Trello
    board'iga ega (Ezza sotuv / Melores Mebel sotuv)."""

    EZZA = "ezza"
    MELORES = "melores"


class LeadStage(str, Enum):
    """13.1-band varonka bosqichlari. CLOSED_WON/CLOSED_LOST ikkalasi ham
    Trello'da bitta "Yopildi" list'iga tushadi (TZ 6.1-band board'da faqat
    5 ta list bor) — g'alaba/yo'qotish farqi faqat shu ustunda saqlanadi."""

    NEW_LEAD = "new_lead"
    CONTACTED = "contacted"
    OFFER_SENT = "offer_sent"
    AGREED = "agreed"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
```

- [ ] **Step 2: Add `AppSetting` columns**

In `bot/db/models/app_setting.py`, add near the other threshold fields:

```python
DEFAULT_SALES_BOARD_LISTS = {
    "ezza": {"new_lead": None, "contacted": None, "offer_sent": None, "agreed": None, "closed": None},
    "melores": {"new_lead": None, "contacted": None, "offer_sent": None, "agreed": None, "closed": None},
}
```

and inside the class:

```python
    # 13.3-band: "uzoq vaqt aloqaga chiqilmagan" mijoz uchun necha kun
    # (foydalanuvchi bilan tasdiqlangan standart: 7). /settings orqali o'zgartiriladi.
    lead_follow_up_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # 6.1-band: {"ezza": {"new_lead": list_id, ...}, "melores": {...}} — har
    # (brand, bosqich) juftligi uchun Trello list ID. `departments.trello_list_id`
    # bilan bir xil naqsh: bot UI orqali EMAS, to'g'ridan-to'g'ri bazada
    # sozlanadi (5-bosqich hujjatiga qarang).
    sales_board_lists: Mapped[dict] = mapped_column(JSON, nullable=False)
```

- [ ] **Step 3: Migration**

Check current head first: `cd bot && .venv\Scripts\alembic heads` (expected: `b3f7a1c9d204`). Then create
`bot/db/migrations/versions/<new_rev>_phase5_sales_settings.py` (pick any new 12-char hex revision id, e.g. via `python -c "import uuid; print(uuid.uuid4().hex[:12])"`):

```python
"""phase5 sales settings: lead_follow_up_threshold_days, sales_board_lists

Revision ID: <new_rev>
Revises: b3f7a1c9d204
Create Date: 2026-07-17 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import json


revision = '<new_rev>'
down_revision = 'b3f7a1c9d204'
branch_labels = None
depends_on = None

_DEFAULT_BOARD_LISTS = json.dumps({
    "ezza": {"new_lead": None, "contacted": None, "offer_sent": None, "agreed": None, "closed": None},
    "melores": {"new_lead": None, "contacted": None, "offer_sent": None, "agreed": None, "closed": None},
})


def upgrade() -> None:
    op.add_column(
        'app_settings',
        sa.Column('lead_follow_up_threshold_days', sa.Integer(), nullable=False, server_default='7'),
    )
    op.add_column(
        'app_settings',
        sa.Column('sales_board_lists', sa.JSON(), nullable=False, server_default=_DEFAULT_BOARD_LISTS),
    )


def downgrade() -> None:
    op.drop_column('app_settings', 'sales_board_lists')
    op.drop_column('app_settings', 'lead_follow_up_threshold_days')
```

- [ ] **Step 4: Wire into `settings_service.py`**

Add both fields to `AppSettingsSnapshot` and to `_load_from_db()`'s constructor call (same pattern as `report_time`).

- [ ] **Step 5: Wire `lead_follow_up_threshold_days` into `/settings` generic editor**

In `bot/keyboards/admin_kb.py`, add to `SETTING_FIELD_LABELS`:
```python
    "lead_follow_up_threshold_days": "📞 Lid follow-up chegarasi (kun)",
```

In `bot/handlers/admin/settings.py`, add to `_PROMPTS`:
```python
    "lead_follow_up_threshold_days": "Necha kun aloqa bo'lmasa sotuvchiga eslatma borishini kiriting (masalan: 7):",
```
and extend the existing integer-threshold branch in `_parse_value`:
```python
    if field in ("plus_ball_per_day", "plus_ball_max_days", "financial_flag_threshold_days", "lead_follow_up_threshold_days"):
```
(just add the new field name to that existing tuple — no new branch).

- [ ] **Step 6: Run migration against real Railway DB**

```bash
cd bot && .venv\Scripts\alembic upgrade head
```
Expected: no errors, `alembic current` shows the new revision.

- [ ] **Step 7: Commit**

```bash
git add bot/utils/enums.py bot/db/models/app_setting.py bot/services/settings_service.py bot/keyboards/admin_kb.py bot/handlers/admin/settings.py bot/db/migrations/versions/
git commit -m "Phase 5: lead/brand enums + sales settings fields"
```

---

### Task 2: `Lead` and `CallLog` models + repositories + migration

**Files:**
- Create: `bot/db/models/lead.py`
- Create: `bot/db/models/call_log.py`
- Modify: `bot/db/models/__init__.py`
- Modify: `bot/db/models/client.py` (add `leads` relationship — optional but keeps ORM consistent; skip if not needed for queries used here — **skip it**, no code path needs `Client.leads`)
- Modify: `bot/db/models/employee.py` (no change needed — FK is one-directional, no back_populates required since nothing queries `Employee.leads` in this plan)
- Create: `bot/db/repositories/lead_repo.py`
- Create: `bot/db/repositories/call_log_repo.py`
- Modify: `bot/db/repositories/__init__.py`
- Create: `bot/db/migrations/versions/<rev2>_phase5_leads_call_logs.py`

**Interfaces:**
- Consumes: `LeadBrand`, `LeadStage` from Task 1.
- Produces: `Lead(id, client_id, brand, stage, assigned_seller_id, trello_card_id, last_contacted_at)`.
- Produces: `CallLog(id, lead_id, recorded_by_id, content, audio_file_id, called_at)`.
- Produces: `LeadRepository.list_by_seller(employee_id, *, open_only=True) -> list[Lead]`, `LeadRepository.list_stale_open(threshold: datetime) -> list[Lead]`.
- Produces: `CallLogRepository.list_by_lead(lead_id) -> list[CallLog]`.

- [ ] **Step 1: `bot/db/models/lead.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase
from utils.enums import LeadBrand, LeadStage

if TYPE_CHECKING:
    from db.models.client import Client
    from db.models.employee import Employee


class Lead(TimestampedBase):
    """13.1-band: sotuv varonkasi lidi. Ishlab chiqarish `tasks` jadvalidan
    TO'LIQ mustaqil — muddat/KPI jarima tizimiga umuman kirmaydi (5-bosqich
    hujjatidagi arxitektura qarori)."""

    __tablename__ = "leads"

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", name="fk_leads_client_id"), nullable=False)
    brand: Mapped[LeadBrand] = mapped_column(
        Enum(LeadBrand, name="lead_brand", native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    stage: Mapped[LeadStage] = mapped_column(
        Enum(LeadStage, name="lead_stage", native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=LeadStage.NEW_LEAD,
        nullable=False,
    )
    assigned_seller_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", name="fk_leads_assigned_seller_id"), nullable=False
    )
    trello_card_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 13.3-band: eng oxirgi qo'ng'iroq vaqti (yoki lid yaratilgan vaqt, hali
    # qo'ng'iroq bo'lmagan bo'lsa) — `jobs/lead_follow_up_job.py` shu ustunga
    # qarab "uzoq aloqasiz" lidlarni topadi (har safar join/aggregate qilish
    # o'rniga, `sales_service.add_call_log()` yozganda yangilanadi).
    last_contacted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    client: Mapped["Client"] = relationship()
    assigned_seller: Mapped["Employee"] = relationship()
```

- [ ] **Step 2: `bot/db/models/call_log.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.employee import Employee
    from db.models.lead import Lead


class CallLog(TimestampedBase):
    """13.2-band: qo'ng'iroqlar bazasi. Qo'lda kiritish (matn yoki Telegram
    ovozli xabar) — IP-telefoniya integratsiyasi KEYINGI, alohida loyihalash
    talab qiladigan ish (provayder hali tanlanmagan, foydalanuvchi bilan
    tasdiqlangan)."""

    __tablename__ = "call_logs"

    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", name="fk_call_logs_lead_id"), nullable=False)
    recorded_by_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", name="fk_call_logs_recorded_by_id"), nullable=False
    )
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    lead: Mapped["Lead"] = relationship()
    recorded_by: Mapped["Employee"] = relationship()
```

- [ ] **Step 3: Register in `bot/db/models/__init__.py`**

Add `Lead`/`CallLog` imports and `__all__` entries, alphabetically ordered like the existing list.

- [ ] **Step 4: `bot/db/repositories/lead_repo.py`**

```python
from datetime import datetime

from sqlalchemy import select

from db.models.lead import Lead
from db.repositories.base import BaseRepository
from utils.enums import LeadStage

_CLOSED_STAGES = (LeadStage.CLOSED_WON, LeadStage.CLOSED_LOST)


class LeadRepository(BaseRepository[Lead]):
    model = Lead

    async def list_by_seller(self, employee_id: int, *, open_only: bool = True) -> list[Lead]:
        stmt = select(Lead).where(Lead.assigned_seller_id == employee_id)
        if open_only:
            stmt = stmt.where(Lead.stage.notin_(_CLOSED_STAGES))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_stale_open(self, threshold: datetime) -> list[Lead]:
        """13.3-band: ochiq lidlar, oxirgi aloqadan beri `threshold`dan oldin
        (`jobs/lead_follow_up_job.py`, kunlik)."""
        result = await self.session.execute(
            select(Lead).where(
                Lead.stage.notin_(_CLOSED_STAGES),
                Lead.last_contacted_at < threshold,
            )
        )
        return list(result.scalars().all())
```

- [ ] **Step 5: `bot/db/repositories/call_log_repo.py`**

```python
from sqlalchemy import select

from db.models.call_log import CallLog
from db.repositories.base import BaseRepository


class CallLogRepository(BaseRepository[CallLog]):
    model = CallLog

    async def list_by_lead(self, lead_id: int) -> list[CallLog]:
        result = await self.session.execute(
            select(CallLog).where(CallLog.lead_id == lead_id).order_by(CallLog.called_at.desc())
        )
        return list(result.scalars().all())
```

- [ ] **Step 6: Register in `bot/db/repositories/__init__.py`**

Add `LeadRepository`/`CallLogRepository` imports + `__all__` entries.

- [ ] **Step 7: Migration**

`bot/db/migrations/versions/<rev2>_phase5_leads_call_logs.py`, `down_revision` = the Task 1 migration's revision id:

```python
"""phase5 leads and call_logs tables

Revision ID: <rev2>
Revises: <rev from Task 1>
Create Date: 2026-07-17 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '<rev2>'
down_revision = '<rev from Task 1>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'leads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('brand', sa.String(length=20), nullable=False),
        sa.Column('stage', sa.String(length=20), nullable=False),
        sa.Column('assigned_seller_id', sa.Integer(), nullable=False),
        sa.Column('trello_card_id', sa.String(length=50), nullable=True),
        sa.Column('last_contacted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name='fk_leads_client_id'),
        sa.ForeignKeyConstraint(['assigned_seller_id'], ['employees.id'], name='fk_leads_assigned_seller_id'),
    )
    op.create_table(
        'call_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('recorded_by_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('audio_file_id', sa.String(length=200), nullable=True),
        sa.Column('called_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], name='fk_call_logs_lead_id'),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['employees.id'], name='fk_call_logs_recorded_by_id'),
    )


def downgrade() -> None:
    op.drop_table('call_logs')
    op.drop_table('leads')
```

- [ ] **Step 8: Run migration + commit**

```bash
cd bot && .venv\Scripts\alembic upgrade head
git add bot/db/models/lead.py bot/db/models/call_log.py bot/db/models/__init__.py bot/db/repositories/lead_repo.py bot/db/repositories/call_log_repo.py bot/db/repositories/__init__.py bot/db/migrations/versions/
git commit -m "Phase 5: leads + call_logs tables and repositories"
```

---

### Task 3: `services/sales_service.py`

**Files:**
- Create: `bot/services/sales_service.py`

**Interfaces:**
- Consumes: `TrelloClient.create_card`, `TrelloClient.move_card_to_list` (`trello/client.py`, unchanged); `client_service.find_or_create_client` (unchanged); `settings_service.get_settings()`.
- Produces: `create_lead(*, brand: LeadBrand, client_phone: str, client_full_name: str, seller_id: int) -> Lead`, `advance_lead_stage(lead_id: int) -> Lead`, `close_lead(lead_id: int, *, won: bool) -> Lead`, `add_call_log(lead_id: int, recorded_by_id: int, *, content: str | None, audio_file_id: str | None) -> CallLog`, exceptions `LeadNotFoundError`, `SalesBoardNotConfiguredError`, `InvalidLeadStateError`.

- [ ] **Step 1: Write the module**

```python
"""13.1/13.2-band: Sotuv CRM — lidlar varonkasi + qo'ng'iroqlar bazasi.
Ishlab chiqarish domenidan (tasks/task_assignments/penalty_service) TO'LIQ
mustaqil (5-bosqich hujjatidagi arxitektura qarori) — o'z jadval to'plami,
o'z servisi.

Trello yozish tartibi `task_service.create_task()` bilan bir xil qoida:
AVVAL Trello'da karta ochiladi/ko'chiriladi, FAQAT shu muvaffaqiyatli
bo'lsagina bazaga yoziladi/yangilanadi."""

import logging
from datetime import datetime, timezone

from config import settings
from core.database import async_session
from db.models.call_log import CallLog
from db.models.lead import Lead
from db.repositories import CallLogRepository, LeadRepository
from services import client_service, settings_service
from trello.client import TrelloClient
from utils.enums import LeadBrand, LeadStage

logger = logging.getLogger(__name__)

# 13.1-band: varonka ILGARI YO'NALISHDA shu tartibda o'tadi. Yopish (won/lost)
# istalgan ochiq bosqichdan mumkin — shu sabab alohida `close_lead()` bor.
_FORWARD_ORDER = [LeadStage.NEW_LEAD, LeadStage.CONTACTED, LeadStage.OFFER_SENT, LeadStage.AGREED]

# TZ 6.1-band: board'da faqat 5 ta list bor (Yangi lid/Aloqa/Taklif/Kelishildi/
# Yopildi) — CLOSED_WON va CLOSED_LOST ikkalasi ham "closed" list'iga tushadi.
_STAGE_TO_LIST_KEY = {
    LeadStage.NEW_LEAD: "new_lead",
    LeadStage.CONTACTED: "contacted",
    LeadStage.OFFER_SENT: "offer_sent",
    LeadStage.AGREED: "agreed",
    LeadStage.CLOSED_WON: "closed",
    LeadStage.CLOSED_LOST: "closed",
}


class LeadNotFoundError(Exception):
    """Berilgan lead_id topilmadi."""


class SalesBoardNotConfiguredError(Exception):
    """Berilgan (brand, bosqich) juftligi uchun Trello list ID
    `app_settings.sales_board_lists`da sozlanmagan."""


class InvalidLeadStateError(Exception):
    """So'ralgan amal lidning joriy bosqichiga mos kelmaydi."""


async def _resolve_list_id(brand: LeadBrand, stage: LeadStage) -> str:
    board_lists = (await settings_service.get_settings()).sales_board_lists
    list_id = board_lists.get(brand.value, {}).get(_STAGE_TO_LIST_KEY[stage])
    if not list_id:
        raise SalesBoardNotConfiguredError(
            f"'{brand.value}' uchun '{stage.value}' bosqichida Trello list sozlanmagan"
        )
    return list_id


async def create_lead(
    *, brand: LeadBrand, client_phone: str, client_full_name: str, seller_id: int
) -> Lead:
    client = await client_service.find_or_create_client(phone_number=client_phone, full_name=client_full_name)
    list_id = await _resolve_list_id(brand, LeadStage.NEW_LEAD)

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        card = await trello.create_card(list_id=list_id, name=client_full_name, desc=f"Tel: {client_phone}")

    now = datetime.now(timezone.utc)
    async with async_session() as session:
        lead = await LeadRepository(session).create(
            client_id=client.id,
            brand=brand,
            stage=LeadStage.NEW_LEAD,
            assigned_seller_id=seller_id,
            trello_card_id=card["id"],
            last_contacted_at=now,
        )
        await session.commit()
        return lead


async def advance_lead_stage(lead_id: int) -> Lead:
    async with async_session() as session:
        repo = LeadRepository(session)
        lead = await repo.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError(f"Lead {lead_id} topilmadi")
        if lead.stage not in _FORWARD_ORDER:
            raise InvalidLeadStateError(f"Lead {lead_id} yopilgan yoki noma'lum bosqichda ({lead.stage})")

        current_index = _FORWARD_ORDER.index(lead.stage)
        if current_index == len(_FORWARD_ORDER) - 1:
            raise InvalidLeadStateError(f"Lead {lead_id} allaqachon so'nggi ochiq bosqichda ({lead.stage})")
        next_stage = _FORWARD_ORDER[current_index + 1]
        brand = lead.brand
        card_id = lead.trello_card_id

    list_id = await _resolve_list_id(brand, next_stage)
    if card_id:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card_id, list_id)

    async with async_session() as session:
        repo = LeadRepository(session)
        lead = await repo.get_by_id(lead_id)
        await repo.update(lead, stage=next_stage)
        await session.commit()
        return lead


async def close_lead(lead_id: int, *, won: bool) -> Lead:
    async with async_session() as session:
        repo = LeadRepository(session)
        lead = await repo.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError(f"Lead {lead_id} topilmadi")
        if lead.stage in (LeadStage.CLOSED_WON, LeadStage.CLOSED_LOST):
            raise InvalidLeadStateError(f"Lead {lead_id} allaqachon yopilgan ({lead.stage})")
        brand = lead.brand
        card_id = lead.trello_card_id

    target_stage = LeadStage.CLOSED_WON if won else LeadStage.CLOSED_LOST
    list_id = await _resolve_list_id(brand, target_stage)
    if card_id:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card_id, list_id)

    async with async_session() as session:
        repo = LeadRepository(session)
        lead = await repo.get_by_id(lead_id)
        await repo.update(lead, stage=target_stage)
        await session.commit()
        return lead


async def add_call_log(
    lead_id: int, recorded_by_id: int, *, content: str | None, audio_file_id: str | None
) -> CallLog:
    """13.2-band. `content`/`audio_file_id`dan kamida bittasi bo'lishi
    kerak — bo'sh qo'ng'iroq yozuvi ma'nosiz."""
    if not content and not audio_file_id:
        raise ValueError("Qo'ng'iroq matni yoki ovozli xabardan kamida bittasi kerak")

    now = datetime.now(timezone.utc)
    async with async_session() as session:
        lead_repo = LeadRepository(session)
        lead = await lead_repo.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError(f"Lead {lead_id} topilmadi")

        call_log = await CallLogRepository(session).create(
            lead_id=lead_id,
            recorded_by_id=recorded_by_id,
            content=content,
            audio_file_id=audio_file_id,
            called_at=now,
        )
        await lead_repo.update(lead, last_contacted_at=now)
        await session.commit()
        return call_log
```

- [ ] **Step 2: Smoke-verify** (see Task 6 for the full script — this task's
  slice is just `create_lead` + `advance_lead_stage` + `close_lead` + `add_call_log`
  called directly from a Python REPL against the Test board, confirming no
  exceptions and that `lead.trello_card_id` moved list on each call).

- [ ] **Step 3: Commit**

```bash
git add bot/services/sales_service.py
git commit -m "Phase 5: sales_service (lead funnel + call logs)"
```

---

### Task 4: Notification + follow-up job

**Files:**
- Modify: `bot/services/notification_service.py`
- Create: `bot/jobs/lead_follow_up_job.py`
- Modify: `bot/main.py` (register the new cron job)

**Interfaces:**
- Consumes: `LeadRepository.list_stale_open`, `settings_service.get_settings().lead_follow_up_threshold_days`.
- Produces: `notification_service.notify_lead_follow_up(bot, lead_id) -> None`.

- [ ] **Step 1: Add to `notification_service.py`**

Add `LeadRepository` to the existing repository imports, then append:

```python
async def notify_lead_follow_up(bot: Bot, lead_id: int) -> None:
    """13.3-band: mas'ul sotuvchiga "uzoq aloqasiz lid" eslatmasi
    (`jobs/lead_follow_up_job.py`, kunlik — chegaradan ortiq turgan har
    kuni qayta yuboriladi, TZ "avtomatik eslatma bo'lib boradi" iborasi
    bir martalik emas, davomiy signalni nazarda tutadi)."""
    async with async_session() as session:
        lead = await LeadRepository(session).get_by_id(lead_id)
        if lead is None:
            logger.warning("notify_lead_follow_up: lead %s topilmadi", lead_id)
            return

        client = await ClientRepository(session).get_by_id(lead.client_id)
        seller = await EmployeeRepository(session).get_by_id(lead.assigned_seller_id)
        if seller is None:
            return

    client_name = client.full_name if client else "noma'lum mijoz"
    days_idle = (datetime.now(timezone.utc) - lead.last_contacted_at.replace(tzinfo=timezone.utc)).days
    text = f"📞 \"{client_name}\" bilan {days_idle} kundan beri aloqa yo'q. Qo'ng'iroq qiling."
    await _send(bot, seller.telegram_id, text)
```

(Add `from db.repositories import ... LeadRepository` to the existing import
block; add `from datetime import datetime, timezone` to the top-level import
— check first whether `datetime`/`timezone` are already imported in this file;
if not, add them.)

- [ ] **Step 2: `bot/jobs/lead_follow_up_job.py`**

```python
"""13.3-band: kunlik job — uzoq vaqt aloqaga chiqilmagan (ochiq) lidlarni
topib, mas'ul sotuvchiga eslatma yuboradi. `core/scheduler.py` orqali
`main.py`da kunlik ro'yxatdan o'tkaziladi."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from core.database import async_session
from db.repositories import LeadRepository
from services import notification_service, settings_service

logger = logging.getLogger(__name__)


async def run(bot: Bot) -> None:
    threshold_days = (await settings_service.get_settings()).lead_follow_up_threshold_days
    threshold = datetime.now(timezone.utc) - timedelta(days=threshold_days)

    async with async_session() as session:
        leads = await LeadRepository(session).list_stale_open(threshold)
        lead_ids = [lead.id for lead in leads]

    for lead_id in lead_ids:
        try:
            await notification_service.notify_lead_follow_up(bot, lead_id)
        except Exception:
            logger.exception("lead_follow_up_job: notify_lead_follow_up xatosi (lead_id=%s)", lead_id)

    logger.info("lead_follow_up_job yakunlandi: %s ta eslatma", len(lead_ids))
```

- [ ] **Step 3: Register in `main.py`**

Add import `from jobs import ..., lead_follow_up_job` (alphabetical in the
existing `from jobs import daily_sync_job, overdue_watch_job, reminder_job, report_job`
line -> becomes `from jobs import daily_sync_job, lead_follow_up_job, overdue_watch_job, reminder_job, report_job`),
then add near the other `scheduler.add_job` calls:

```python
    scheduler.add_job(
        lead_follow_up_job.run, "cron", hour=10, minute=0, args=[bot], id="lead_follow_up_job"
    )
```

- [ ] **Step 4: Commit**

```bash
git add bot/services/notification_service.py bot/jobs/lead_follow_up_job.py bot/main.py
git commit -m "Phase 5: lead follow-up reminder job"
```

---

### Task 5: Seller-facing handlers (`handlers/sales/leads.py`) + keyboards + states + router wiring

**Files:**
- Create: `bot/keyboards/sales_kb.py`
- Create: `bot/states/sales_states.py`
- Create: `bot/handlers/sales/leads.py`
- Modify: `bot/main.py` (router registration, remove the sales TODO comment)

**Interfaces:**
- Consumes: `sales_service.create_lead/advance_lead_stage/close_lead/add_call_log`, `EmployeeRepository`, `RoleAccessMiddleware`.
- Produces: `/yangilid`, `/lidlarim` commands for `Role.SELLER`.

- [ ] **Step 1: `bot/states/sales_states.py`**

```python
from aiogram.fsm.state import State, StatesGroup


class CreateLeadStates(StatesGroup):
    """13.1-band: sotuvchi yangi lid kiritish oqimi (/yangilid)."""

    waiting_for_brand = State()
    waiting_for_phone = State()
    waiting_for_name = State()


class CallLogStates(StatesGroup):
    """13.2-band: lidga qo'ng'iroq yozuvi qo'shish — matn yoki ovozli xabar."""

    waiting_for_content = State()
```

- [ ] **Step 2: `bot/keyboards/sales_kb.py`**

```python
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models.lead import Lead
from utils.enums import LeadBrand

BRAND_LABELS: dict[LeadBrand, str] = {
    LeadBrand.EZZA: "Ezza",
    LeadBrand.MELORES: "Melores Mebel",
}

STAGE_LABELS: dict[str, str] = {
    "new_lead": "🆕 Yangi lid",
    "contacted": "📞 Aloqa qilindi",
    "offer_sent": "📄 Taklif berildi",
    "agreed": "🤝 Kelishildi",
    "closed_won": "✅ Yopildi (g'alaba)",
    "closed_lost": "❌ Yopildi (bekor)",
}


class BrandSelect(CallbackData, prefix="leadbrand"):
    brand: str


class LeadSelect(CallbackData, prefix="leadsel"):
    lead_id: int


class LeadAdvance(CallbackData, prefix="leadadv"):
    lead_id: int


class LeadClose(CallbackData, prefix="leadclose"):
    lead_id: int
    won: bool


class LeadCallLogStart(CallbackData, prefix="leadcall"):
    lead_id: int


def build_brand_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=BrandSelect(brand=brand.value).pack())]
        for brand, label in BRAND_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_lead_list_keyboard(leads: list[Lead]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{STAGE_LABELS.get(lead.stage.value, lead.stage.value)} — lead #{lead.id}",
                callback_data=LeadSelect(lead_id=lead.id).pack(),
            )
        ]
        for lead in leads
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_lead_detail_keyboard(lead: Lead) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📞 Qo'ng'iroq qo'shish", callback_data=LeadCallLogStart(lead_id=lead.id).pack())]]
    if lead.stage.value in ("new_lead", "contacted", "offer_sent"):
        rows.append([InlineKeyboardButton(text="➡️ Keyingi bosqich", callback_data=LeadAdvance(lead_id=lead.id).pack())])
    if lead.stage.value not in ("closed_won", "closed_lost"):
        rows.append([
            InlineKeyboardButton(text="✅ Yopish (g'alaba)", callback_data=LeadClose(lead_id=lead.id, won=True).pack()),
            InlineKeyboardButton(text="❌ Yopish (bekor)", callback_data=LeadClose(lead_id=lead.id, won=False).pack()),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 3: `bot/handlers/sales/leads.py`**

```python
"""13-band: Sotuvchi (Role.SELLER) uchun lid varonkasi + qo'ng'iroqlar
bazasi. Ishlab chiqarish handlerlaridan (worker/admin) mustaqil — o'z rol
tekshiruvi, o'z FSM oqimi."""

import logging

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.repositories import EmployeeRepository, LeadRepository
from keyboards.sales_kb import (
    BrandSelect,
    LeadAdvance,
    LeadCallLogStart,
    LeadClose,
    LeadSelect,
    STAGE_LABELS,
    build_brand_keyboard,
    build_lead_detail_keyboard,
    build_lead_list_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import sales_service
from states.sales_states import CallLogStates, CreateLeadStates
from utils.enums import LeadBrand, Role

logger = logging.getLogger(__name__)

router = Router(name="sales_leads")
router.message.middleware(RoleAccessMiddleware({Role.SELLER}))
router.callback_query.middleware(RoleAccessMiddleware({Role.SELLER}))


@router.message(Command("yangilid"))
async def cmd_new_lead(message: Message, state: FSMContext) -> None:
    try:
        await state.set_state(CreateLeadStates.waiting_for_brand)
        await message.answer("Qaysi brand uchun yangi lid?", reply_markup=build_brand_keyboard())
    except Exception:
        logger.exception("cmd_new_lead xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.message(Command("cancel"), StateFilter(CreateLeadStates))
async def cmd_cancel_new_lead(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.callback_query(CreateLeadStates.waiting_for_brand, BrandSelect.filter())
async def on_brand_selected(callback: CallbackQuery, callback_data: BrandSelect, state: FSMContext) -> None:
    try:
        await state.update_data(brand=callback_data.brand)
        await state.set_state(CreateLeadStates.waiting_for_phone)
        if callback.message:
            await callback.message.edit_text("Mijoz telefon raqamini kiriting:")
        await callback.answer()
    except Exception:
        logger.exception("on_brand_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(CreateLeadStates.waiting_for_phone)
async def on_lead_phone_received(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if not phone:
        await message.answer("Telefon raqami bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return
    await state.update_data(phone=phone)
    await state.set_state(CreateLeadStates.waiting_for_name)
    await message.answer("Mijoz F.I.Sh. kiriting:")


@router.message(CreateLeadStates.waiting_for_name)
async def on_lead_name_received(message: Message, state: FSMContext, employee) -> None:
    full_name = (message.text or "").strip()
    if not full_name:
        await message.answer("Ism bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return

    data = await state.get_data()
    await state.clear()

    try:
        lead = await sales_service.create_lead(
            brand=LeadBrand(data["brand"]),
            client_phone=data["phone"],
            client_full_name=full_name,
            seller_id=employee.id,
        )
    except sales_service.SalesBoardNotConfiguredError as exc:
        await message.answer(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_lead_name_received xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await message.answer(f"✅ Lid yaratildi (#{lead.id}), Trello karta: {lead.trello_card_id}")


@router.message(Command("lidlarim"))
async def cmd_my_leads(message: Message, state: FSMContext, employee) -> None:
    try:
        await state.clear()
        async with async_session() as session:
            leads = await LeadRepository(session).list_by_seller(employee.id)

        if not leads:
            await message.answer("Sizda ochiq lid yo'q.")
            return

        await message.answer("Sizning ochiq lidlaringiz:", reply_markup=build_lead_list_keyboard(leads))
    except Exception:
        logger.exception("cmd_my_leads xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


async def _show_lead_detail(answer_func, lead_id: int) -> None:
    async with async_session() as session:
        lead = await LeadRepository(session).get_by_id(lead_id)
    if lead is None:
        await answer_func("Lid topilmadi.")
        return
    text = f"Lid #{lead.id} — {STAGE_LABELS.get(lead.stage.value, lead.stage.value)}"
    await answer_func(text, reply_markup=build_lead_detail_keyboard(lead))


@router.callback_query(LeadSelect.filter())
async def on_lead_selected(callback: CallbackQuery, callback_data: LeadSelect) -> None:
    try:
        if callback.message:
            await _show_lead_detail(callback.message.edit_text, callback_data.lead_id)
        await callback.answer()
    except Exception:
        logger.exception("on_lead_selected xatosi (lead_id=%s)", callback_data.lead_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(LeadAdvance.filter())
async def on_lead_advance(callback: CallbackQuery, callback_data: LeadAdvance) -> None:
    try:
        await sales_service.advance_lead_stage(callback_data.lead_id)
    except (sales_service.LeadNotFoundError, sales_service.InvalidLeadStateError, sales_service.SalesBoardNotConfiguredError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        logger.exception("on_lead_advance xatosi (lead_id=%s)", callback_data.lead_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    if callback.message:
        await _show_lead_detail(callback.message.edit_text, callback_data.lead_id)
    await callback.answer("Yangilandi ✅")


@router.callback_query(LeadClose.filter())
async def on_lead_close(callback: CallbackQuery, callback_data: LeadClose) -> None:
    try:
        await sales_service.close_lead(callback_data.lead_id, won=callback_data.won)
    except (sales_service.LeadNotFoundError, sales_service.InvalidLeadStateError, sales_service.SalesBoardNotConfiguredError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        logger.exception("on_lead_close xatosi (lead_id=%s)", callback_data.lead_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    if callback.message:
        await _show_lead_detail(callback.message.edit_text, callback_data.lead_id)
    await callback.answer("Yopildi ✅")


@router.callback_query(LeadCallLogStart.filter())
async def on_call_log_start(callback: CallbackQuery, callback_data: LeadCallLogStart, state: FSMContext) -> None:
    try:
        await state.set_state(CallLogStates.waiting_for_content)
        await state.update_data(lead_id=callback_data.lead_id)
        if callback.message:
            await callback.message.answer("Qo'ng'iroq haqida matn yozing yoki ovozli xabar yuboring:")
        await callback.answer()
    except Exception:
        logger.exception("on_call_log_start xatosi (lead_id=%s)", callback_data.lead_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(Command("cancel"), StateFilter(CallLogStates))
async def cmd_cancel_call_log(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.message(CallLogStates.waiting_for_content)
async def on_call_log_content_received(message: Message, state: FSMContext, employee) -> None:
    data = await state.get_data()
    await state.clear()

    content = message.text if message.text else None
    audio_file_id = message.voice.file_id if message.voice else None

    if not content and not audio_file_id:
        await message.answer("Matn yoki ovozli xabar kerak. Qayta urinib ko'ring: /lidlarim")
        return

    try:
        await sales_service.add_call_log(
            data["lead_id"], employee.id, content=content, audio_file_id=audio_file_id
        )
    except sales_service.LeadNotFoundError as exc:
        await message.answer(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_call_log_content_received xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await message.answer("✅ Qo'ng'iroq yozuvi saqlandi.")
```

- [ ] **Step 4: Wire into `main.py`**

Replace the line:
```python
    # TODO: handlers/ ichidagi qolgan routerlarni (sales) shu yerga qo'shish
```
with:
```python
    dp.include_router(sales_leads_router)
```
and add the import (alphabetically among the other handler imports):
```python
from handlers.sales.leads import router as sales_leads_router
```

- [ ] **Step 5: Commit**

```bash
git add bot/keyboards/sales_kb.py bot/states/sales_states.py bot/handlers/sales/leads.py bot/main.py
git commit -m "Phase 5: seller-facing lead handlers (/yangilid, /lidlarim)"
```

---

### Task 6: Docs + real-infra smoke verification

**Files:**
- Modify: `shared/db-schema.md` (add `leads`, `call_logs` tables; add `app_settings.lead_follow_up_threshold_days`/`sales_board_lists`)
- Modify: `.claude/plans/05-sotuv-crm.md` (status header -> "Bajarilgan", note the 3 decisions taken with the user, note IP-telephony deferral)
- Modify: `.claude/plans/README.md` (status row for 5-bosqich)
- Create (temp): `bot/_smoke_phase5_sales.py`

- [ ] **Step 1: Write the smoke script**

```python
"""Vaqtinchalik: 5-bosqich (Sotuv CRM) smoke test. Real Railway DB + Trello
"Test" board'ga qarshi ishlaydi. Ishlatilgach o'chiriladi (CLAUDE.md convention)."""

import asyncio

from core.database import async_session
from db.repositories import (
    CallLogRepository, ClientRepository, EmployeeRepository, LeadRepository,
)
from services import sales_service, settings_service
from utils.enums import LeadBrand, Role


async def main() -> None:
    # 0. Pastga sales_board_lists["ezza"] barcha kalitlarini haqiqiy Test
    # board list ID'lari bilan bazada qo'lda to'ldirib qo'ying (bitta martalik
    # SQL UPDATE), aks holda SalesBoardNotConfiguredError chiqadi.
    settings = await settings_service.get_settings()
    assert settings.sales_board_lists["ezza"]["new_lead"], "avval sales_board_lists ni to'ldiring"

    async with async_session() as session:
        seller = next(
            (e for e in await EmployeeRepository(session).list_by_role(Role.SELLER) if e.is_active),
            None,
        )
    assert seller is not None, "kamida bitta faol SELLER xodim kerak"

    lead = await sales_service.create_lead(
        brand=LeadBrand.EZZA, client_phone="+998900000001", client_full_name="Smoke Test Client", seller_id=seller.id
    )
    assert lead.trello_card_id

    lead = await sales_service.advance_lead_stage(lead.id)
    assert lead.stage.value == "contacted"

    call_log = await sales_service.add_call_log(lead.id, seller.id, content="Sinov qo'ng'irog'i", audio_file_id=None)
    assert call_log.id

    lead = await sales_service.close_lead(lead.id, won=True)
    assert lead.stage.value == "closed_won"

    # Tozalash
    async with async_session() as session:
        await CallLogRepository(session).delete(call_log)
        lead_row = await LeadRepository(session).get_by_id(lead.id)
        await LeadRepository(session).delete(lead_row)
        client_row = await ClientRepository(session).get_by_phone_number("+998900000001")
        if client_row:
            await ClientRepository(session).delete(client_row)
        await session.commit()

    print("Phase 5 smoke test OK")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Fill `sales_board_lists` on the Test board and run it**

```bash
cd bot && .venv\Scripts\python _smoke_phase5_sales.py
```
Expected output: `Phase 5 smoke test OK`.

- [ ] **Step 3: Delete the smoke script**

```bash
rm bot/_smoke_phase5_sales.py
```

- [ ] **Step 4: Update `shared/db-schema.md`, `.claude/plans/05-sotuv-crm.md`, `.claude/plans/README.md`**

Document the two new tables, the two new `app_settings` columns, and flip
the status the same way earlier phases record completion (see how Phase 3/4
did it in the same files).

- [ ] **Step 5: Commit**

```bash
git add shared/db-schema.md .claude/plans/05-sotuv-crm.md .claude/plans/README.md
git commit -m "Phase 5: docs + status update (sales CRM done, IP-telephony deferred)"
```

---

## Self-Review

- **Spec coverage**: A (Trello structure) -> Task 1 (`sales_board_lists`) + Task 3 (`_resolve_list_id`). B (funnel) -> Task 3/5. C (call log, manual-entry branch only, per user decision) -> Task 2/3/5. D (follow-up) -> Task 4. Role/permissions -> `RoleAccessMiddleware({Role.SELLER})` in Task 5. Migration gotchas (server_default, FK names) -> Tasks 1/2. Verification plan (dedicated Test board, smoke script, cleanup) -> Task 6.
- **Not built** (explicitly, by user decision): IP-telephony webhook/provider integration, and any bot UI for editing `sales_board_lists` (mirrors the existing no-UI precedent for `departments.trello_list_id`).
- **Placeholder scan**: no TBD/"add error handling later" left in any step; every step has runnable code.
- **Type consistency**: `LeadStage`/`LeadBrand` used identically across `lead.py`, `sales_service.py`, `sales_kb.py`, `leads.py`. `sales_service.create_lead/advance_lead_stage/close_lead/add_call_log` signatures match their call sites in `handlers/sales/leads.py` and the smoke script.
