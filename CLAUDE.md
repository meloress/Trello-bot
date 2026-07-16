# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A production/KPI management system for a furniture manufacturing company (Melores Mebel), built on Trello + a Telegram bot + a web admin panel. Full spec: `Trello_Telegram_TZ_v2.1_ToLiq.docx` / `TZ_content.txt` (Uzbek). Core business goal: automatically detect underperforming employees via per-task KPI penalties, driven off deadlines tracked in Postgres (not Trello itself, which has no timers or automatic labeling).

Three parts sharing one Postgres database:
- `bot/` — Python + aiogram v3.22.0. This is where essentially all real functionality lives: Telegram bot, Trello sync, timers, KPI/penalty calculation, scheduler. **This is almost always the directory you'll be working in.**
- `web/` — Node/Express admin panel. Currently an empty skeleton (static file server only, no routes/DB/UI wired up). Do not assume functionality exists here without checking.
- `shared/db-schema.md` — hand-maintained source-of-truth doc for the DB schema. **Update this whenever you change `bot/db/models/`.**

Only `bot/` (via Alembic) may run migrations. `web/` reads/writes the existing schema but never alters it.

## Commands

All commands run from `bot/`, using the venv at `bot/.venv` (already configured as the VS Code interpreter via `.vscode/settings.json`).

```
# Setup
cd bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Run the bot
python main.py
```

Web panel (skeleton only): `cd web && npm install && npm start` (or `npm run dev` for nodemon).

**There is no automated test suite** (`bot/tests/` is an empty scaffold, no pytest in `requirements.txt`). Verification is done by writing a one-off script that calls services directly against the **real** Railway Postgres DB and, for Trello-touching work, the real Trello account's dedicated **"Test"** board — never the production **"Fasad seh"** board. Pattern used throughout this codebase's history: write a temp `bot/_smoke_<feature>.py` script, run it with `.venv/Scripts/python`, assert expected DB/Trello state, then delete test rows (watch FK ordering — see Gotchas) and delete the script when done.

## Architecture

### Layering (strict, one-way)

```
handlers/  → services/  → db/repositories/  → db/models/
              ↓
           trello/client.py
```

- **`db/models/`** — SQLAlchemy 2.0 `Mapped`/`mapped_column` models. All inherit `TimestampedBase` (`db/base.py`), which supplies `id`/`created_at`/`updated_at` — never redeclare these. Enums (`utils/enums.py`: `Role`, `TaskStatus`, `TaskType`) are stored `native_enum=False` (plain VARCHAR + no CHECK constraint) so adding a new enum value is a cheap additive migration, not a blocking `ALTER TYPE`.
- **`db/repositories/`** — one class per model extending `BaseRepository` (generic CRUD: `get_by_id`, `list_all`, `create`, `update`, `delete`). Repositories only `flush()`, never `commit()`. Add query methods here, not ad-hoc queries in services.
- **`services/`** — business logic, one module per concern (not classes — this is a deliberate, consistent choice across the codebase: `task_service`, `timer_service`, `penalty_service`, `notification_service`, `stats_service`, `settings_service`, `employee_service`, `registration_service`, `trello_sync_service`). Each public function is its own **Unit of Work**: opens `async_session()`, does repository calls, `commit()`s, returns live ORM objects. This works safely because the session maker uses `expire_on_commit=False` (`core/database.py`) — returned objects stay readable after commit without a re-query.
- **`handlers/`** — aiogram routers, split by role: `admin/`, `worker/`, `brigadier/`, `common/` (`supervisor/`, `sales/` exist but are empty — not yet built). Each handler splits into two blocks: the primary business call (fails loud, aborts on error) and secondary effects like notifications/UI updates (wrapped in `try/except`, logged only — a failed notification must never make the user think their action failed).
- **`trello/client.py`** — thin `aiohttp` wrapper, `async with TrelloClient(...)`. Only implements what's actually used (cards, labels, list-move) — no checklists, members, comments, or webhooks yet.

### Exceptions

Each service module defines its own exception classes (`TaskNotFoundError`, `InvalidTaskStateError`, `DepartmentNotConfiguredError`, `PenaltyRuleNotConfiguredError`, etc.) rather than sharing a common hierarchy. Handlers catch these by name and translate to user-facing Uzbek text; anything unexpected falls through to a generic `except Exception` + `logger.exception` + generic error message, so a bug never silently fails a Telegram interaction.

### FSM / CallbackData conventions

- Multi-step admin flows use `aiogram.fsm` `StatesGroup`s (`states/*.py`), one file per flow.
- `CallbackData` factories live in `keyboards/*_kb.py`. **Some are reused across multiple unrelated flows** (e.g. `DepartmentSelect`, `EmployeeToggle`, `BrigadeSelect`) — when adding a new handler for one of these, always scope your `@router.callback_query(...)` with the specific FSM state (or `StateFilter(None)` for the entry point) rather than a bare `.filter()`, or you'll collide with another router's handler for the same callback prefix. Grep for the CallbackData class name first to see existing usages before wiring a new one.
- Timezone: Tashkent is fixed UTC+5 (no DST) — hardcoded as `TASHKENT_TZ` in `utils/formatters.py` and re-declared locally in a couple of handler files. Deadlines are entered as `DD.MM.YYYY HH:MM` local time and stored as timezone-aware UTC.

### Production task lifecycle (the core domain model)

A `tasks` row is either `task_type=order` (backed by a real Trello card) or `task_type=misc` (a Trello-free ad-hoc assignment, `trello_card_id` always NULL). Orders move through a **chain of departments** (e.g. Stolyar → Shkurka → Kraska), each hop being its own `tasks` row:

- `departments.next_department_id` (self-FK) defines the standard pipeline; `NULL` = final stage.
- `tasks.previous_task_id` (self-FK) chains a stage back to its predecessor; multiple stage-rows share the same `trello_card_id` (not unique — only *one* non-`COMPLETED` row per card is "current" at a time, an app-level invariant, not a DB constraint).
- Finishing a stage (`timer_service.finish_task`) is deliberately **not** where stage-advancement happens — `task_service.advance_task_stage()` is called separately, only from the worker's "Yakunlash" handler, never from `finish_task` itself or from `daily_sync_job`'s Trello-archive-triggered auto-close path (archiving a card means the *whole order* terminated, not "advance to next stage" — conflating these two was a real bug caught during development).
- A new stage starts life as `status=PENDING_SETUP` with `deadline=NULL` — the system does not invent a per-department SLA; a supervisor/admin must enter the deadline and assign employees (`activate_pending_stage`) before the timer effectively starts being checked. `jobs/daily_sync_job.py` explicitly excludes `PENDING_SETUP` rows from its open-tasks scan.
- Read `shared/db-schema.md`'s `tasks` table section for the full narrative — it's kept current and is the fastest way to re-orient on this subsystem.

### Settings: two different mechanisms, don't confuse them

- `app_settings` (singleton table, `services/settings_service.py`, in-process cached) — exactly 4 scalar knobs: `remind_time`, `default_penalty_multiplier`, `brigade_share_ratio`, `balls_per_day_shift`. Edited via `/settings`.
- `penalty_rules` table — the actual late-penalty bracket schedule (variable number of `[min_hours_late, max_hours_late) → score` rows, optionally department-specific, global fallback via `department_id IS NULL`). Adding a new bracket is a data change, not a schema/code change. An hours-late value not covered by any rule raises `PenaltyRuleNotConfiguredError` — it deliberately does **not** fall back to the nearest known bracket.
- Some values are still hardcoded constants pending business confirmation, e.g. `BASE_PAYMENT_DAY = 15` in `penalty_service.py`, and `calculate_plus_ball()` is a stub returning `0` (bonus-point criteria not yet decided). Check `shared/db-schema.md` before assuming a number is configurable.

## Gotchas

- **Circular FK**: `brigades.brigadier_id` ↔ `employees.brigade_id`. Alembic autogenerate warns about an "unresolvable cycle" — harmless, ignore it. But when deleting test data, null out both FK columns before deleting rows, or you'll hit `ForeignKeyViolationError`.
- **Named constraints**: Alembic autogenerate sometimes emits `op.create_foreign_key(None, ...)` / unnamed unique constraints, which breaks `downgrade()`. Always give explicit names when hand-editing a migration (repo convention: `fk_<table>_<column>`).
- **New NOT NULL columns on non-empty tables** need a `server_default` in the migration or `alembic upgrade` fails.
- **`postgresql+asyncpg://`**: `DATABASE_URL` in `.env` is plain `postgresql://` (Railway's format); `config.settings.async_database_url` rewrites the scheme. Use `settings.async_database_url` for the engine, never `settings.database_url` directly.
- Trello card operations should generally happen **before** the corresponding DB write commits (see `task_service.create_task`'s docstring) — the failure mode to avoid is a DB row with no backing Trello card, not the reverse.
