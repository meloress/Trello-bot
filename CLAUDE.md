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
100%: gaps found against explicit TZ requirements (not open
questions) — no Trello card comment on "Stop" (§7.5), the card-label
automation only covers 3 of TZ's 5 states and never reflects STOPPED (§6.3),
no department-level stats cut (§10.1), and no "everyone can see all open
misc tasks" list (§9). (The web-panel employee-add UI gap, §4.2, has since
been closed — see "Web panel" below.)
Phase 6 splits into two very different pieces: **Part A** (end-to-end smoke
test + production launch) is ordinary engineering work — `bot/_smoke_e2e_full.py`
exercises the full lifecycle (create → overdue →
8.3 reassignment → late penalty → multi-stage advance → early-finish plus
ball → client notification → stats → report) against the real Trello
"Test" board, and `bot/railway.json` is the deploy config for running the
bot as its own Railway service (chosen host — same project as the existing
Postgres; `restartPolicyType: ON_FAILURE` covers the 16-band auto-restart
requirement natively, no systemd/pm2 needed). The Railway deploy itself has
now happened (driven by the Mini App work — see "Mini App" below — via
Railway's GitHub auto-deploy, public domain enabled), but that's `.claude/plans/06`'s
step B only: the E2E smoke test hasn't been run and `departments.trello_list_id`
still points at the "Test" board, not production ("Fasad seh") — don't treat
Phase 6-A as fully closed. **Parts B/C/D** (Ping billing, multi-tenant
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

**There is no automated test suite** (`bot/tests/` is an empty scaffold, no pytest in `requirements.txt`). Verification is done by writing a one-off script that calls services directly against the **real** Railway Postgres DB and, for Trello-touching work, a real Trello board — never the production **"Fasad seh"** board (see Gotchas below before assuming the "Test" board is a safe target). Pattern used throughout this codebase's history: write a temp `bot/_smoke_<feature>.py` script, run it with `.venv/Scripts/python`, assert expected DB/Trello state, then delete test rows (watch FK ordering — see Gotchas) and delete the script when done. `bot/_seed_demo_data.py` is a **different, standing** script (deliberately *not* prefix-matched or deleted like the `_smoke_*` ones) that populates a full realistic dataset — org structure, multi-stage tasks in every status, KPI history, financial suggestions, sales leads — via the real service layer against a **brand-new Trello board it creates itself** (`TrelloClient.create_board`/`create_list`); re-run it any time a fresh demo/walkthrough dataset is needed, but it errors on duplicate names/phones if run twice without clearing prior demo rows first.

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
- **`handlers/`** — aiogram routers. Deliberately tiny now: only `common/start.py` (`/start` — registration + a Mini App button, and a `StateFilter(None)` catch-all that redirects any other idle-state message to the Mini App) and `common/client_link.py` (`/mijoz` — clients aren't employees and can't open the Mini App, so this one flow stays chat-only). Every other role-specific flow that used to live under `handlers/admin/`, `handlers/worker/`, `handlers/brigadier/`, `handlers/sales/` has been fully ported into `miniapp/api/*.py` and those directories were deleted — see "Mini App" below. The "primary business call fails loud, secondary effects (notifications) are `try/except`-wrapped and logged-only" split still applies, just inside `miniapp/api/*.py` now.
- **`trello/client.py`** — thin `aiohttp` wrapper, `async with TrelloClient(...)`. Only implements what's actually used (boards, lists, cards, labels, list-move, members, checklists) — no comments or webhooks yet.

### Web panel (`web/`) — a separate app, not a client of `bot/`

`web/` is plain Node/Express with no framework and no build step (paths are `web/src/public/`, not `web/public/`). It cannot import `bot/`'s Python code, so anywhere its logic needs to match `bot/services/*.py` (`stats_service.py`'s monthly-stats query, and now `employee_service.py`'s create/validation rules), the logic is **hand-duplicated** in `web/src/routes/*.js` — if you change the grouping/filtering logic in `stats_service.py` or the validation/duplicate-check rules in `employee_service.py`, update the matching JS too, there's no shared source of truth to keep them in sync automatically.

- **Auth** (`web/src/auth.js`): one shared password (`WEB_ADMIN_PASSWORD`) compared with `crypto.timingSafeEqual`, no user table. Sessions are a stateless signed cookie (`HMAC-SHA256` over an expiry timestamp, keyed by `WEB_SESSION_SECRET`) — no session store, no extra dependency, survives server restarts by design.
- **Frontend** (`public/js/app.js`, vanilla JS, no framework): single-page "one window" layout per TZ §4.1 — the dashboard is one page; secondary views (ranking, employee-add) open in a **modal** rather than a route — reuse the existing `.modal`/`.modal-content` pattern for any new secondary view rather than adding page routing. Charts use Chart.js loaded from a CDN `<script>` tag, not an npm package.
- **Design system** (`public/css/style.css`): a real token system (`--surface-*`, `--ink*`, `--accent*`, `--positive`/`--critical`, etc.) defined once in `:root`, redefined under `@media (prefers-color-scheme: dark)` **and** `html[data-theme="dark"]`/`html[data-theme="light"]` (the toggle button in the topbar stamps `data-theme` on `<html>`, persisted to `localStorage`) — style new components through the tokens, never hardcoded hex, so both themes stay correct automatically. `--positive`/`--critical` (used by the stats-table chips and the score chart) are a **validated colorblind-safe pair** (`#008300` / `#e34948` light, `#008300` / `#e66767` dark) — don't swap these for "nicer-looking" green/red without re-running the dataviz skill's `validate_palette.js` (see Gotchas: an earlier green/red pair looked fine but failed the CVD check outright).
- **Employee-add** (`web/src/routes/employees.js` + `web/src/trello.js`): the one write path in `web/` besides login. `POST /api/employees` hand-duplicates `bot/services/employee_service.py`'s duplicate-name/phone checks and `employee_management.py`'s phone regex, plus computes `next_payment_date` itself (the 15th-of-month default is a Python model default, not a DB default — a raw SQL insert must set it explicitly or it lands `NULL`). `web/src/trello.js` mirrors `TrelloClient.get_member_id` using Node's built-in `fetch` (no HTTP client dependency). The form's single "Trello username or Gmail" field auto-detects by `@`: an `@` routes to `gmail` with no Trello lookup; anything else is looked up as a Trello username (404 → user-facing error, not silently accepted).
- A Telegram Mini App now exists (`bot/miniapp/`) — see the dedicated "Mini App" section below. This supersedes the earlier "no Mini App, deliberate choice" stance, and has since gone further: the bot is now **Mini-App-only** for every operational role — chat commands/inline keyboards for admin/worker/brigadier/seller flows were removed entirely, not kept as a parallel interface.
- Routes live under `/api/*` (`web/src/routes/`), each protected by the `requireAuth` middleware from `auth.js`.

### Mini App (`bot/miniapp/`) — the only operational UI now; chat is just the front door

A Telegram Mini App (WebView opened from an inline `web_app` button, `keyboards/miniapp_kb.build_miniapp_button()`, or the persistent Menu Button set in `main.py`) is now the **sole** interface for all six roles — every admin/worker/brigadier/seller flow that used to have a chat command or inline keyboard has been ported here and the old `handlers/admin/`, `handlers/worker/`, `handlers/brigadier/`, `handlers/sales/` directories (and their `states/*.py`/`keyboards/*_kb.py` support files) were deleted. Chat now only handles `/start` (registration + Mini App button) and `/mijoz` (client self-linking — clients aren't employees and can't open the Mini App); any other message gets a `StateFilter(None)` catch-all in `handlers/common/start.py` that just points at the Mini App button. Unlike `web/`, the Mini App is **not** a separate Node app: `bot/main.py` runs an `aiohttp.web` server (`miniapp/server.py`) *inside the same process* as the polling loop via `asyncio.gather()` — no new deploy target, no logic duplicated in a second language. Every endpoint calls the exact same `services/*.py` functions the old chat handlers used (`task_service`, `timer_service`, `penalty_service`, `employee_service`, `settings_service`, `financial_service`, `sales_service`, `stats_service`) — the one deliberate exception to the "hand-duplicate in the other language" pattern `web/` established, chosen specifically because these are **write** paths with real side effects (Trello card moves, KPI penalties); duplicating that logic in JS was rejected as the highest-risk kind of divergence bug.

- **Auth**: Telegram WebApp `initData` (HMAC-SHA256, keyed by `SHA256(bot_token)` per Telegram's own spec) verified in `miniapp/auth.py`'s `auth_middleware`, sent by the frontend as an `X-Telegram-Init-Data` header on every `fetch()` (never as a URL param — Telegram doesn't append anything to the WebApp URL itself, the frontend reads `Telegram.WebApp.initData` client-side). Resolves to an `Employee` via `telegram_id` — the only identity check left in the system now that chat-side `RoleAccessMiddleware` is gone. Role-gating is done at the **sub-app** level, not per-handler decorators: `/api/miniapp/admin`, `/brigadier`, `/seller` are separate nested `aiohttp.web.Application`s each with their own `role_middleware(...)`, mounted under the parent `api_app` (which only requires "is an active employee") — `request["employee"]` set by the parent's `auth_middleware` propagates through to sub-app middlewares since it's the same `Request` object. `common`/`worker` routes carry no role gate — worker actions rely on task *assignment*, not role.
- **Resource-ownership checks are per-endpoint code, NOT automatic** — `auth_middleware`/`role_middleware` only prove "this is a real, active employee of role X"; they say nothing about whether the caller owns the specific `task_id`/`lead_id`/`employee_id` in the URL. A real-DB audit (2026-07-22) found several endpoints that skipped this and let any authenticated caller act on any other employee's records — since fixed, and now the required pattern for every new endpoint that takes a resource id: `miniapp/api/worker.py`'s `_is_assigned(task_id, employee_id)` gates `start`/`stop`/`resume`/`finish`/task-detail (a `common`/`worker` route reachable by any role, so the task-assignment check *is* the only authorization); `miniapp/api/brigadier.py`'s `_employee_in_scope()` restricts `/members/{employee_id}/...` to the requester's own brigade (BRIGADIER) or department (SUPERVISOR), and `_resolve_brigade()`'s `brigade_id` query param is likewise clamped to the requester's own department, not taken at face value; `miniapp/api/seller.py`'s `_own_lead()` restricts `/leads/{lead_id}/...` to `lead.assigned_seller_id == employee.id`. When adding a new endpoint under an id path param, ask "could a different employee of the same allowed role pass a different id here" — if yes, it needs one of these checks or a new one shaped like them.
- **Getting the `Bot` instance inside a handler**: use `request.config_dict["bot"]`, **never** `request.app["bot"]`. `app["bot"] = bot` is only ever set on the root `aiohttp.web.Application`, and aiohttp's `add_subapp()` does **not** chain state to child apps (no automatic inheritance at any depth) — `request.app` returns whichever (sub-)app owns the matched route, so for `/admin`, `/brigadier`, `/seller` handlers (two levels of subapp nesting) `request.app["bot"]` raises `KeyError` even though it happens to work for `common`/`worker` routes (one level, and only because `notify_task_started` etc. wrap it in `try/except` — the equivalent unwrapped `bot = request.app["bot"]` in `stop_task`/`finish_task` would 500). `request.config_dict` is aiohttp's built-in `ChainMapProxy` across every ancestor app in `match_info.apps` and is the only reliable way to read root-level state from arbitrarily nested sub-apps — found and fixed via the `_smoke_*` real-DB verification workflow (see Commands section), not by inspection.
- **Frontend** (`miniapp/public/`, vanilla JS/CSS, no build step, no framework): reuses the web panel's validated design tokens as a **static copy** (`public/css/app.css` — bot can't import `web/`'s CSS across languages) since Telegram WebApp messages can't be styled any other way. Navigation is two layers: a persistent **bottom tab-bar** (`#tabbar`, `tabDefsForRole()`/`renderTabBar()` in `app.js`, rendered fresh after every screen change) picks the active section per role (Worker: Buyurtmalar/Vazifalar/Ball/Profil; Admin/Supervisor: Bosh sahifa/Statistika/Xodimlar/Moliyaviy/Profil, with Sozlamalar reachable from Profil rather than as its own tab; Brigadier: Brigada/Profil; Seller: Lidlarim/Profil), and within a section a JS-side push/pop stack (`nav.stack`) drives Telegram's native `BackButton` for drill-down screens (task detail, employee edit, etc.) — `switchTab()` resets the stack, `show()`/`goBack()` push/pop within it, and `replaceTop()` re-renders the current top-of-stack entry in place (same screen, fresh data) **without** growing or wiping the stack — use this, not `show()`, for "refresh this same screen after an action" (e.g. after a toggle/save that isn't navigating anywhere) and not `resetTo()` for "switch what this screen displays" (e.g. the new-task form's Order/Misc segmented control) unless the screen is genuinely a tab root with nothing below it to preserve — a 2026-07-22 audit found ~15 call sites conflating these three and either corrupting the back-stack (`resetTo()` from a non-root screen silently drops its ancestors) or pushing duplicate/self-referential entries (`goBack()` immediately followed by `show()` of the very screen `goBack()` already re-rendered, or `show()` of the screen already on top). The primary action per screen is always Telegram's native `MainButton` (never an in-page "submit" button) — `setMainButton()`/`hideMainButton()` wrap it. Real per-screen dynamic content (task titles, employee names, department names) is **not** translated — only UI chrome (labels, statuses, buttons) is, via `public/js/i18n.js`'s `uz`/`ru` dictionary, because those are free text an admin typed in, not strings this system owns a translation for.
- **Language preference**: `employees.language` (`a1c9f3e7d502` migration, default `'uz'`) — set from the Mini App's own Profile screen (`POST /me/language`), not from the chat (no bot command sets it). Switching it re-renders the *entire* app in that language, not just the Profile screen.
- **New task/misc-task creation is a single scrollable form**, not a stepper wizard — `screenNewTaskForm()` uses a segmented Order/Misc control at the top to switch which fields render, rather than a separate flow per task type.
- **Admin home surfaces two queue-style alerts inline** rather than requiring a push-notification tap: `screenAdminHome()` fetches `GET /admin/pending-setup` and `GET /admin/reassign-candidates` alongside the dashboard and renders an `.alert-card` for each non-empty queue (the same lists the old "Sozlash"/"Ko'rib chiqish" notification buttons used to open) — `notification_service.notify_stage_pending_setup`/`notify_reassignment_candidate` still push a heads-up DM, but plain-text now (no `reply_markup`), pointing at the Mini App section instead of an inline button. `notify_task_started` (the "you've been assigned" DM) is the one notification that **does** still attach a button — a `keyboards.miniapp_kb.build_miniapp_button()` inline keyboard — since that message is the primary way a brigadier/worker learns to open the app at all; don't assume all notifications follow the plain-text-only pattern.
- **Deploy note**: `config.settings.port` (env `PORT`, default `8080`) is the Mini App's listen port; `config.settings.miniapp_base_url` (env `MINIAPP_BASE_URL`) must be a public HTTPS URL for the `web_app` button / `bot.set_chat_menu_button()` call in `main.py` to activate at all — both are skipped silently (not an error) when unset, so the bot keeps polling fine in local dev with no public domain (just with a dead Mini App button). **Deployed and live** on the bot's Railway service (public domain enabled, `MINIAPP_BASE_URL` set) — the same always-on service that already ran the polling loop, not a new one; the user deploys via Railway's GitHub auto-deploy (push to `origin/main`), not via Railway CLI from this session.
- **`aiohttp`'s `add_static` does not serve `index.html` for the bare `/` request** — it treats `/` as a directory listing and 403s when `show_index=False` (which this app always sets). Telegram always opens a Mini App at `/`, so this hit every single launch until `server.py` added an explicit `app.router.add_get("/", _index)` *before* the `add_static` call. If you add more static-serving paths, remember plain `add_static` alone never covers the root of that path.

### Exceptions

Each service module defines its own exception classes (`TaskNotFoundError`, `InvalidTaskStateError`, `DepartmentNotConfiguredError`, `PenaltyRuleNotConfiguredError`, etc.) rather than sharing a common hierarchy. Handlers catch these by name and translate to user-facing Uzbek text; anything unexpected falls through to a generic `except Exception` + `logger.exception` + generic error message, so a bug never silently fails a Telegram interaction.

### Remaining chat FSM conventions

Only two `StatesGroup`s are left (`states/registration_states.py`, `states/client_states.py`) since every other multi-step flow moved into the Mini App's REST endpoints (no FSM there — each screen just does a fetch). `handlers/common/start.py`'s `StateFilter(None)` catch-all means any new chat `StatesGroup` **must** get its state-specific handlers registered before that catch-all would otherwise intercept free-text input meant for the new flow — mirror the existing `RegistrationStates`/`ClientLinkStates` pattern (state-specific handler in its own router, checked in `main.py`'s router-inclusion order) rather than adding raw `@router.message()` handlers with no state filter.

- Timezone: Tashkent is fixed UTC+5 (no DST) — hardcoded as `TASHKENT_TZ` in `utils/formatters.py`. Mini App deadlines are picked via `<input type="datetime-local">` and converted client-side (`app.js`) before being sent as ISO 8601 UTC; chat's old `DD.MM.YYYY HH:MM` local-time parsing is gone along with the handlers that did it.
- Worker task/score views (`GET /tasks`, `/misctasks`, `/score` in `miniapp/api/worker.py`) are split by `TaskType` the same way the old `/tasks`/`/misctasks`/`/myscore` commands were — `ORDER` and `MISC` never merge in one list, and score uses `penalty_service.month_bounds()` + `KpiLogRepository.list_by_employee_in_range()`, newest-first.

### Production task lifecycle (the core domain model)

A `tasks` row is either `task_type=order` (backed by a real Trello card) or `task_type=misc` (a Trello-free ad-hoc assignment, `trello_card_id` always NULL). Orders move through a **chain of departments** (e.g. Stolyar → Shkurka → Kraska), each hop being its own `tasks` row:

- `departments.next_department_id` (self-FK) defines the standard pipeline; `NULL` = final stage.
- `tasks.previous_task_id` (self-FK) chains a stage back to its predecessor; multiple stage-rows share the same `trello_card_id` (not unique — only *one* non-`COMPLETED` row per card is "current" at a time, an app-level invariant, not a DB constraint).
- Finishing a stage (`timer_service.finish_task`) is deliberately **not** where stage-advancement happens — `task_service.advance_task_stage()` is called separately, only from the worker's "Yakunlash" handler, never from `finish_task` itself or from `daily_sync_job`'s Trello-archive-triggered auto-close path (archiving a card means the *whole order* terminated, not "advance to next stage" — conflating these two was a real bug caught during development).
- A new stage starts life as `status=PENDING_SETUP` with `deadline=NULL` — the system does not invent a per-department SLA; a supervisor/admin must enter the deadline and assign employees (`activate_pending_stage`) before the timer effectively starts being checked. `jobs/daily_sync_job.py` explicitly excludes `PENDING_SETUP` rows from its open-tasks scan.
- Trello card membership and the "Bosqichlar" checklist track the same chain: `task_service.create_task()` adds assigned employees as real card members (via `employees.trello_member_id`, resolved once at employee-creation time) and creates one checklist item per department in the chain; `advance_task_stage()` checks off the just-finished department and drops its employees from the card; `activate_pending_stage()` re-adds the new stage's employees. All of this is a secondary effect (logged on failure, never blocks the primary DB write).
- **Assignment is two-stage, not direct-to-worker**: `create_task()`/`activate_pending_stage()` are still generic (`employee_ids: list[int]`), but the Mini App now always calls them with a **single** id — the department's brigadier (picked via `GET /admin/departments/{id}/brigadiers`, `miniapp/api/admin.py`), never a worker directly. The brigadier is therefore the sole `task_assignments` row and the deadline clock runs against them. `notify_task_started` pings the brigadier to open the Mini App; there they see the task in their "🆕 Yangi ish" queue (`GET /brigadier/pending-delegation`) and call `POST /brigadier/tasks/{id}/delegate` (`task_service.delegate_task()`) to hand it to specific worker(s) from **their own brigade only** (`EmployeeRepository.list_by_brigade`, enforced in `miniapp/api/brigadier.py` before the service call) — this fully replaces the brigadier's `task_assignments` row with the chosen worker(s), the same "no partial/co-assignment, full handoff" rule `reassign_task_brigade()` already used. `notify_task_started` fires again for the newly-assigned worker(s). The brigadier keeps earning their `brigade_share_ratio` KPI cut regardless (`penalty_service` derives it from `brigades.brigadier_id`, not from `task_assignments` membership) — but note `penalty_service` only ever scores `Role.WORKER` assignees, so a task a brigadier never delegates produces **no** KPI penalty for anyone when it goes overdue/finishes, a known gap in this design, not yet addressed.
- `jobs/overdue_watch_job.py` runs hourly (alongside `daily_sync_job.py`'s daily Trello-label sync) and owns three independent things: flagging "1 day left", flipping `ACTIVE`/`STOPPED` tasks past their deadline to `OVERDUE`, and — for departments with `auto_reassign_after_48h=True` — signaling tasks overdue by 48h+ for manual brigade reassignment. The actual brigade swap is always a human decision (Mini App's "🔁 Ko'rib chiqish kutilmoqda" queue, `miniapp/api/admin.py`'s `reassign_task` → `task_service.reassign_task_brigade()`), which penalizes the old brigade immediately and stamps `tasks.reassigned_at` so the eventual completion penalty is computed from that timestamp instead of the original `deadline` (no double-penalizing the new brigade for time it didn't own).
- Read `shared/db-schema.md`'s `tasks` table section for the full narrative — it's kept current and is the fastest way to re-orient on this subsystem.

### Settings: three different mechanisms, don't confuse them

- `app_settings` (singleton table, `services/settings_service.py`, in-process cached) — scalar knobs: `default_penalty_multiplier`, `brigade_share_ratio`, `balls_per_day_shift`, `plus_ball_per_day`, `plus_ball_max_days`, `financial_flag_threshold_days`, `advance_threshold_percent`, `advance_waiver_percent`, `report_time`, `lead_follow_up_threshold_days`, plus `reminder_schedule`: a JSON list of `{"time": "HH:MM", "urgency": "info"|"warning"|"urgent"}` entries so the daily reminder can escalate through the day. Scalars are edited via the Mini App's Sozlamalar screen (`GET/POST /admin/settings`, `miniapp/api/admin.py`); the reminder list has its own `GET/POST/PUT/DELETE /admin/reminders` CRUD there. Any change to `reminder_schedule` calls `jobs/reminder_job.schedule_all()` (and any change to `report_time` calls `jobs/report_job.schedule_all()`), which tears down and re-registers the corresponding APScheduler jobs to match — job count always mirrors current settings, don't assume a fixed set of job ids.
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
always typed in by hand** by an admin, now via the Mini App's Moliyaviy tab
(`miniapp/api/admin.py`): the pending-list + `POST /financial/{id}/amount`
endpoint lists wage-deduction flags and takes the withheld amount
(`financial_service.set_wage_deduction_amount`); `POST /financial/advance-waiver`
walks through the same advance-waiver inputs (task id, advance %, order
value, late?) and calls `create_advance_waiver_suggestion`. Both are still
just data entry — they create/update a suggestion row, never approve or
transfer anything.

### Client notifications (12-band) — Telegram-only by design

`clients` (`db/models/client.py`) is a separate, deliberately minimal table (name/phone/`telegram_id`) linked from `tasks.client_id` (nullable — never set for `task_type=misc`). A client is created/matched by phone number when an admin builds a task (`services/client_service.find_or_create_client`, wired into the Mini App's `POST /admin/tasks` as an optional step, `miniapp/api/admin.py`); the client then self-links their own Telegram account by phone via `/mijoz` (`handlers/common/client_link.py` — the one remaining chat-only flow, same "admin pre-creates the record, the person links themself" pattern as employee registration in `registration_service.py`). `notification_service.notify_client_stage_advanced`/`notify_client_task_stopped` fire from `miniapp/api/worker.py`'s `finish_task`/`stop_task` (not from `task_service`/`timer_service` — same secondary-effect convention as everywhere else) and no-op silently if `client_id` or the client's `telegram_id` is `NULL`. SMS was an open TZ question (§19 #11) and was explicitly resolved as Telegram-only — don't add an SMS gateway without re-confirming that decision changed.

### Sales CRM (13-band, Phase 5) — a fully separate domain from `tasks`

`leads` (`db/models/lead.py`) and `call_logs` (`db/models/call_log.py`) are their own table pair, deliberately **not** built on `tasks`/`task_assignments`/`penalty_service` — leads have no deadline, no KPI penalty, no department chain. A lead belongs to a `brand` (`LeadBrand`: `ezza`/`melores`) and moves through a `stage` (`LeadStage`) via `services/sales_service.py`: `advance_lead_stage()` only steps forward through `NEW_LEAD → CONTACTED → OFFER_SENT → AGREED`; closing (`close_lead(won=...)`) can happen from any open stage straight to `CLOSED_WON`/`CLOSED_LOST` — both of those map to the same Trello list ("Yopildi"), since the TZ 6.1-band board only has 5 lists, not 6. Which Trello list a given `(brand, stage)` maps to comes from `app_settings.sales_board_lists` (see Settings section above) — not configured yet raises `SalesBoardNotConfiguredError`. Call logging (`sales_service.add_call_log`) is manual-only (typed into the Mini App's Lidlarim tab, `miniapp/api/seller.py`'s `POST /leads/{id}/calls`) and updates `leads.last_contacted_at`, which `jobs/lead_follow_up_job.py` (daily, 10:00) uses to nudge the assigned seller about stale open leads — re-sent every day the lead stays stale, not a one-shot signal. IP-telephony integration (an automatic call-log source) was explicitly scoped out — no provider was named in the TZ, and building a webhook receiver with nothing to receive from would be dead code; don't add one without confirming a provider first.

## Gotchas

- **The Trello "Test" board is not a clean sandbox** — discovered 2026-07-17: it contains at least one list with real-looking customer orders (e.g. specific names/addresses in card titles), not just throwaway test fixtures. Treat it as "don't touch, ambiguous provenance" rather than "safe to modify freely." For any new Trello-touching verification work, create a fresh dedicated board (`TrelloClient.create_board`) rather than assuming "Test" is empty/disposable — `bot/_seed_demo_data.py` does exactly this.
- **`core/database.py`'s engine has `pool_pre_ping=True`** — added after a real incident where a `_seed_demo_data.py` run hung indefinitely mid-script with zero error output. Cause: Railway's Postgres proxy silently drops idle connections; without pre-ping, SQLAlchemy hands out a dead connection and the query just hangs forever (no timeout configured anywhere in the stack). Don't remove this to "simplify" the engine config.
- **Circular FK**: `brigades.brigadier_id` ↔ `employees.brigade_id`. Alembic autogenerate warns about an "unresolvable cycle" — harmless, ignore it. But when deleting test data, null out both FK columns before deleting rows, or you'll hit `ForeignKeyViolationError`.
- **Named constraints**: Alembic autogenerate sometimes emits `op.create_foreign_key(None, ...)` / unnamed unique constraints, which breaks `downgrade()`. Always give explicit names when hand-editing a migration (repo convention: `fk_<table>_<column>`).
- **New NOT NULL columns on non-empty tables** need a `server_default` in the migration or `alembic upgrade` fails.
- **`postgresql+asyncpg://`**: `DATABASE_URL` in `.env` is plain `postgresql://` (Railway's format); `config.settings.async_database_url` rewrites the scheme. Use `settings.async_database_url` for the engine, never `settings.database_url` directly.
- Trello card operations should generally happen **before** the corresponding DB write commits (see `task_service.create_task`'s docstring) — the failure mode to avoid is a DB row with no backing Trello card, not the reverse.
- **`web/` and `bot/` share one `.env`**: both `config.py` (`env_file=BASE_DIR/".env"`, where `BASE_DIR` is the repo root, not `bot/`) and `server.js` (`dotenv.config({ path: '../.env' })`, relative to `web/`'s cwd) resolve to the same root-level `.env` — don't create a second `.env` inside `web/` or `bot/`, it won't be picked up.
- **`web/src/routes/stats.js` duplicates `stats_service.py` SQL by hand** (see "Web panel" above) — a stats/KPI logic change on the Python side silently goes stale on the dashboard unless you update both.
- **Don't eyeball chart/status colors — validate them.** A green/red pair chosen by eye for the web dashboard (score chips, chart bars) looked fine but measured ΔE 4–5 on a deuteranopia (red-green colorblind) check — a hard fail, not a style nit. Use the `dataviz` skill's `scripts/validate_palette.js` before shipping any categorical/status color pair; the current `--positive`/`--critical` tokens in `web/src/public/css/style.css` are the validated result.
- **Headless Edge screenshot QA (Windows) can silently fail to load CDN scripts** (e.g. Chart.js) under its default/reused profile — Edge's "Tracking Prevention" blocks jsdelivr, leaving the page half-rendered with no thrown error visible in a plain screenshot. If a headless verification screenshot looks suspiciously faded/blank, rerun with a fresh `--user-data-dir` before assuming the code is broken.
- **`msedge --headless=new --window-size=W,H` does not reliably render at `W` CSS pixels** — observed `window.innerWidth` coming back ~100px wider than the requested `--window-size` value, with no error or warning. A screenshot taken against an assumed width can make correctly-laid-out elements look like they're overflowing the viewport when they aren't. Before concluding a Mini App layout bug from a headless screenshot, inject a script that reports `window.innerWidth`/`getBoundingClientRect()` for the suspect elements (or `console.log` + read devtools) rather than trusting the requested `--window-size` — this cost real time chasing a phantom overflow bug that didn't exist at the actual rendered width.
