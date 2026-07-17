# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A production/KPI management system for a furniture manufacturing company (Melores Mebel), built on Trello + a Telegram bot + a web admin panel. Full spec: `Trello_Telegram_TZ_v2.1_ToLiq.docx` / `TZ_content.txt` (Uzbek). Core business goal: automatically detect underperforming employees via per-task KPI penalties, driven off deadlines tracked in Postgres (not Trello itself, which has no timers or automatic labeling).

Three parts sharing one Postgres database:
- `bot/` — Python + aiogram v3.22.0. This is where almost all real functionality lives: Telegram bot, Trello sync, timers, KPI/penalty calculation, scheduler. **This is almost always the directory you'll be working in.**
- `web/` — Node/Express admin panel (Phase 4: monthly stats table + Chart.js chart + best/worst ranking, single shared-password login). Deliberately thin — TZ §4 scopes it to "view stats, add employees" only, so complex data-entry flows (task creation, client linking, financial suggestions) stay in the Telegram bot's FSM handlers, not here.
- `shared/db-schema.md` — hand-maintained source-of-truth doc for the DB schema. **Update this whenever you change `bot/db/models/`.**

Only `bot/` (via Alembic) may run migrations. `web/` reads/writes the existing schema but never alters it.

## Project status and roadmap

TZ §1-13/16-17 (the production core: employee database, Trello structure,
timers/reminders/Stop, KPI/penalties, stats/dashboard, client notifications,
sales CRM) is implemented and committed — full band-by-band traceability
lives in `shared/db-schema.md` (every table/column cites its TZ section) and
in git history (`git log --oneline` — commits are phase-labeled). `.claude/plans/`
no longer tracks finished phases; as of a full TZ re-audit (2026-07-17,
reading `TZ_content.txt` band-by-band against the actual code) it holds only
**remaining work**, organized as one file per item (`README.md` there is the
current index/status table) — check it before assuming something is done or
undone. That audit found the production core is high-fidelity but not
100%: five concrete gaps against explicit TZ requirements (not open
questions) — no Trello card comment on "Stop" (§7.5), the card-label
automation only covers 3 of TZ's 5 states and never reflects STOPPED (§6.3),
no department-level stats cut (§10.1), no web-panel employee-add UI (§4.2,
still bot-only), and no "everyone can see all open misc tasks" list (§9).
Phase 6 splits into two very different pieces: **Part A** (end-to-end smoke
test + production launch) is ordinary engineering work and is ready to run
— `bot/_smoke_e2e_full.py` exercises the full lifecycle (create → overdue →
8.3 reassignment → late penalty → multi-stage advance → early-finish plus
ball → client notification → stats → report) against the real Trello
"Test" board, and `bot/railway.json` is the deploy config for running the
bot as its own Railway service (chosen host — same project as the existing
Postgres; `restartPolicyType: ON_FAILURE` covers the 16-band auto-restart
requirement natively, no systemd/pm2 needed) — but it hasn't actually been
run/deployed yet. **Parts B/C/D** (Ping billing, multi-tenant
`organization_id` refactor, video lessons) are explicitly out of scope
until a Ping billing contract exists (TZ §19 open question #13) — don't
write real billing/multi-tenant code from a guess at that contract's shape.

Each remaining-work plan documents its own **open questions or decisions
that block implementation** — when a plan says a decision is blocked, don't
guess a business rule to fill the gap; ask. `.claude/plans/07-tz-ochiq-savollar.md`
consolidates TZ §19's own open-question list against current status (most
are resolved with a working default; a couple are genuinely still open).

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

Web panel: `cd web && npm install && npm start` (or `npm run dev` for nodemon). Reads the **same root `.env`** as `bot/` (`dotenv.config({ path: '../.env' })`), plus its own `WEB_ADMIN_PASSWORD`/`WEB_SESSION_SECRET` — `server.js` exits immediately at startup if either is unset.

**There is no automated test suite** (`bot/tests/` is an empty scaffold, no pytest in `requirements.txt`). Verification is done by writing a one-off script that calls services directly against the **real** Railway Postgres DB and, for Trello-touching work, the real Trello account's dedicated **"Test"** board — never the production **"Fasad seh"** board. Pattern used throughout this codebase's history: write a temp `bot/_smoke_<feature>.py` script, run it with `.venv/Scripts/python`, assert expected DB/Trello state, then delete test rows (watch FK ordering — see Gotchas) and delete the script when done.

Production deploy target is **Railway** (`bot/railway.json`, NIXPACKS build, `python main.py` as a long-running polling worker — not a webhook, so no public URL/port needed). Deploy as its own service with Root Directory set to `bot/`; it reads env vars the same way locally (`config.Settings` via `.env`/`BASE_DIR`), so on Railway set `BOT_TOKEN`/`TRELLO_API_KEY`/`TRELLO_TOKEN`/`DATABASE_URL` as service environment variables instead (no `.env` file gets deployed — it's git-ignored).

## Architecture

### Layering (strict, one-way)

```
handlers/  → services/  → db/repositories/  → db/models/
              ↓
           trello/client.py
```

- **`db/models/`** — SQLAlchemy 2.0 `Mapped`/`mapped_column` models. All inherit `TimestampedBase` (`db/base.py`), which supplies `id`/`created_at`/`updated_at` — never redeclare these. Enums (`utils/enums.py`: `Role`, `TaskStatus`, `TaskType`) are stored `native_enum=False` (plain VARCHAR + no CHECK constraint) so adding a new enum value is a cheap additive migration, not a blocking `ALTER TYPE`.
- **`db/repositories/`** — one class per model extending `BaseRepository` (generic CRUD: `get_by_id`, `list_all`, `create`, `update`, `delete`). Repositories only `flush()`, never `commit()`. Add query methods here, not ad-hoc queries in services.
- **`services/`** — business logic, one module per concern (not classes — this is a deliberate, consistent choice across the codebase: `task_service`, `timer_service`, `penalty_service`, `financial_service`, `notification_service`, `stats_service`, `settings_service`, `employee_service`, `registration_service`, `trello_sync_service`, `client_service`, `sales_service`). Each public function is its own **Unit of Work**: opens `async_session()`, does repository calls, `commit()`s, returns live ORM objects. This works safely because the session maker uses `expire_on_commit=False` (`core/database.py`) — returned objects stay readable after commit without a re-query.
- **`handlers/`** — aiogram routers, split by role: `admin/`, `worker/`, `brigadier/`, `common/`, `sales/` (`supervisor/` exists but is still empty — not yet built). Each handler splits into two blocks: the primary business call (fails loud, aborts on error) and secondary effects like notifications/UI updates (wrapped in `try/except`, logged only — a failed notification must never make the user think their action failed).
- **`trello/client.py`** — thin `aiohttp` wrapper, `async with TrelloClient(...)`. Only implements what's actually used (cards, labels, list-move, members, checklists) — no comments or webhooks yet.

### Web panel (`web/`) — a separate app, not a client of `bot/`

`web/` is plain Node/Express with no framework and no build step. It cannot import `bot/`'s Python code, so anywhere its logic needs to match `bot/services/*.py` (currently just `stats_service.py`'s monthly-stats query), the SQL is **hand-duplicated** in `web/src/routes/stats.js` — if you change the grouping/filtering logic in `stats_service.py`, update the matching query in `stats.js` too, there's no shared source of truth to keep them in sync automatically.

- **Auth** (`web/src/auth.js`): one shared password (`WEB_ADMIN_PASSWORD`) compared with `crypto.timingSafeEqual`, no user table. Sessions are a stateless signed cookie (`HMAC-SHA256` over an expiry timestamp, keyed by `WEB_SESSION_SECRET`) — no session store, no extra dependency, survives server restarts by design.
- **Frontend** (`public/js/app.js`, vanilla JS, no framework): single-page "one window" layout per TZ §4.1 — the dashboard is one page; secondary views (the best/worst ranking) open in a modal rather than a route. Charts use Chart.js loaded from a CDN `<script>` tag, not an npm package.
- Routes live under `/api/*` (`web/src/routes/`), each protected by the `requireAuth` middleware from `auth.js`.

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
- Trello card membership and the "Bosqichlar" checklist track the same chain: `task_service.create_task()` adds assigned employees as real card members (via `employees.trello_member_id`, resolved once at employee-creation time) and creates one checklist item per department in the chain; `advance_task_stage()` checks off the just-finished department and drops its employees from the card; `activate_pending_stage()` re-adds the new stage's employees. All of this is a secondary effect (logged on failure, never blocks the primary DB write).
- `jobs/overdue_watch_job.py` runs hourly (alongside `daily_sync_job.py`'s daily Trello-label sync) and owns three independent things: flagging "1 day left", flipping `ACTIVE`/`STOPPED` tasks past their deadline to `OVERDUE`, and — for departments with `auto_reassign_after_48h=True` — signaling tasks overdue by 48h+ for manual brigade reassignment. The actual brigade swap is always a human decision (`handlers/admin/reassign_task.py` → `task_service.reassign_task_brigade()`), which penalizes the old brigade immediately and stamps `tasks.reassigned_at` so the eventual completion penalty is computed from that timestamp instead of the original `deadline` (no double-penalizing the new brigade for time it didn't own).
- Read `shared/db-schema.md`'s `tasks` table section for the full narrative — it's kept current and is the fastest way to re-orient on this subsystem.

### Settings: three different mechanisms, don't confuse them

- `app_settings` (singleton table, `services/settings_service.py`, in-process cached) — scalar knobs: `default_penalty_multiplier`, `brigade_share_ratio`, `balls_per_day_shift`, `plus_ball_per_day`, `plus_ball_max_days`, `financial_flag_threshold_days`, `advance_threshold_percent`, `advance_waiver_percent`, `report_time`, `lead_follow_up_threshold_days`, plus `reminder_schedule`: a JSON list of `{"time": "HH:MM", "urgency": "info"|"warning"|"urgent"}` entries so the daily reminder can escalate through the day. Scalars are edited via `/settings`; the reminder list has its own `/reminders` add/edit/delete flow. Any change to `reminder_schedule` calls `jobs/reminder_job.schedule_all()` (and any change to `report_time` calls `jobs/report_job.schedule_all()`), which tears down and re-registers the corresponding APScheduler jobs to match — job count always mirrors current settings, don't assume a fixed set of job ids.
- `penalty_rules` table — the actual late-penalty bracket schedule (variable number of `[min_hours_late, max_hours_late) → score` rows, optionally department-specific, global fallback via `department_id IS NULL`). Adding a new bracket is a data change, not a schema/code change. An hours-late value not covered by any rule raises `PenaltyRuleNotConfiguredError` — it deliberately does **not** fall back to the nearest known bracket. Brackets currently start at 24h (`[24,48)→-1 … [96,120)→-8`) — `penalty_service.calculate_and_apply_task_penalty` returns no penalty for `hours_late < 24` *in code*, before ever querying this table, so the grace period is a code-level guard, not a `score=0` row.
- **Trello list-id config has no bot UI at all** — both `departments.trello_list_id` (production) and `app_settings.sales_board_lists` (sales, a JSON `{"ezza": {"new_lead": list_id, ...}, "melores": {...}}` map) are configured by writing directly to the DB, not through a Telegram flow. This is a deliberate, repeated precedent, not an oversight — don't build a settings UI for either without checking whether that's actually wanted.
- `BASE_PAYMENT_DAY = 15` in `penalty_service.py` is still a hardcoded constant pending business confirmation (not in the configurable list above). Check `shared/db-schema.md` before assuming a number is configurable.

### Financial suggestions: propose, never execute (8.6-band)

`financial_suggestions` (`db/models/financial_suggestion.py`, `services/financial_service.py`)
is the pattern for anything touching money in this system, which has no
finance module at all (TZ §18 puts that out of scope). Two pure functions
(`calculate_wage_deduction_suggestion`, `calculate_advance_waiver`) do
arithmetic only — no DB, no side effects — and return a result that a thin
wrapper persists with `status='pending_manager_review'`. Nothing in this
codebase ever flips that status to `approved`/`rejected`; that's explicitly
a different, not-yet-built module. Follow this same shape for any future
money-adjacent feature: pure calculation → suggestion row → human decides.
`jobs/overdue_watch_job.py`'s `_process_financial_flags` is the automatic
trigger for wage-deduction flags (long-running stage → suggestion with the
amount left `NULL`, "pending"). Since the system still has no
payment/advance/order-value data source anywhere, **all money inputs are
always typed in by hand** by an admin: `/moliyaviy` (`handlers/admin/financial.py`)
lists pending wage-deduction flags and asks for the withheld amount
(`financial_service.set_wage_deduction_amount`); `/avanskechirim` walks
through advance-waiver inputs (task id, advance %, order value, late?) and
calls `create_advance_waiver_suggestion`. Both are still just data entry —
they create/update a suggestion row, never approve or transfer anything.

### Client notifications (12-band) — Telegram-only by design

`clients` (`db/models/client.py`) is a separate, deliberately minimal table (name/phone/`telegram_id`) linked from `tasks.client_id` (nullable — never set for `task_type=misc`). A client is created/matched by phone number when an admin builds a task (`services/client_service.find_or_create_client`, wired into `handlers/admin/task_create.py`'s FSM as an optional step); the client then self-links their own Telegram account by phone via `/mijoz` (`handlers/common/client_link.py`, same "admin pre-creates the record, the person links themself" pattern as employee registration in `registration_service.py`). `notification_service.notify_client_stage_advanced`/`notify_client_task_stopped` fire from `handlers/worker/tasks.py` (not from `task_service`/`timer_service` — same secondary-effect convention as everywhere else) and no-op silently if `client_id` or the client's `telegram_id` is `NULL`. SMS was an open TZ question (§19 #11) and was explicitly resolved as Telegram-only — don't add an SMS gateway without re-confirming that decision changed.

### Sales CRM (13-band, Phase 5) — a fully separate domain from `tasks`

`leads` (`db/models/lead.py`) and `call_logs` (`db/models/call_log.py`) are their own table pair, deliberately **not** built on `tasks`/`task_assignments`/`penalty_service` — leads have no deadline, no KPI penalty, no department chain. A lead belongs to a `brand` (`LeadBrand`: `ezza`/`melores`) and moves through a `stage` (`LeadStage`) via `services/sales_service.py`: `advance_lead_stage()` only steps forward through `NEW_LEAD → CONTACTED → OFFER_SENT → AGREED`; closing (`close_lead(won=...)`) can happen from any open stage straight to `CLOSED_WON`/`CLOSED_LOST` — both of those map to the same Trello list ("Yopildi"), since the TZ 6.1-band board only has 5 lists, not 6. Which Trello list a given `(brand, stage)` maps to comes from `app_settings.sales_board_lists` (see Settings section above) — not configured yet raises `SalesBoardNotConfiguredError`. Call logging (`sales_service.add_call_log`) is manual-only (Telegram text or voice message via `handlers/sales/leads.py`) and updates `leads.last_contacted_at`, which `jobs/lead_follow_up_job.py` (daily, 10:00) uses to nudge the assigned seller about stale open leads — re-sent every day the lead stays stale, not a one-shot signal. IP-telephony integration (an automatic call-log source) was explicitly scoped out — no provider was named in the TZ, and building a webhook receiver with nothing to receive from would be dead code; don't add one without confirming a provider first.

## Gotchas

- **Circular FK**: `brigades.brigadier_id` ↔ `employees.brigade_id`. Alembic autogenerate warns about an "unresolvable cycle" — harmless, ignore it. But when deleting test data, null out both FK columns before deleting rows, or you'll hit `ForeignKeyViolationError`.
- **Named constraints**: Alembic autogenerate sometimes emits `op.create_foreign_key(None, ...)` / unnamed unique constraints, which breaks `downgrade()`. Always give explicit names when hand-editing a migration (repo convention: `fk_<table>_<column>`).
- **New NOT NULL columns on non-empty tables** need a `server_default` in the migration or `alembic upgrade` fails.
- **`postgresql+asyncpg://`**: `DATABASE_URL` in `.env` is plain `postgresql://` (Railway's format); `config.settings.async_database_url` rewrites the scheme. Use `settings.async_database_url` for the engine, never `settings.database_url` directly.
- Trello card operations should generally happen **before** the corresponding DB write commits (see `task_service.create_task`'s docstring) — the failure mode to avoid is a DB row with no backing Trello card, not the reverse.
- **`web/` and `bot/` share one `.env`**: both `config.py` (`env_file=BASE_DIR/".env"`, where `BASE_DIR` is the repo root, not `bot/`) and `server.js` (`dotenv.config({ path: '../.env' })`, relative to `web/`'s cwd) resolve to the same root-level `.env` — don't create a second `.env` inside `web/` or `bot/`, it won't be picked up.
- **`web/src/routes/stats.js` duplicates `stats_service.py` SQL by hand** (see "Web panel" above) — a stats/KPI logic change on the Python side silently goes stale on the dashboard unless you update both.
