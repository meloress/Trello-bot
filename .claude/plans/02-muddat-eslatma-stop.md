# 2-bosqich: Muddat/taymer rang avtomatikasi, ko'p martali eslatma, "Stop", OVERDUE, Trello a'zo/checklist, 8.3 avto-o'tkazish

Holat: ISHLANMOQDA. DB model o'zgarishlari (app_settings, tasks, employees,
departments) kiritilgan, Alembic migratsiyasi generatsiya qilingan, hali
`server_default` to'g'riligi tekshirilib qo'llanmagan. Servis/handler qatlami
hali boshlanmagan.

TZ manbasi: 7.2 (bildirishnomalar jadvali), 7.3 (kunlik eslatma/jarima vaqt
jadvali), 6.2 (karta talablari: a'zo + checklist), 6.3 (label/rang avtomatikasi),
7.4 (muddat/taymer boshqaruvi), 7.5 (Stop funksiyasi), 8.3 (uzoq kechikishda
avto brigadaga o'tkazish). TZ 17-band jadvalida bu rasman "2-bosqich" deb
nomlangan: "Muddat/taymer va rang avtomatikasi; eslatmalar jadvali
(09:00/13:00/15:00/17:00/18:00); Stop funksiyasi va signallar".

## Hozirda kodda NIMA BOR (boshlang'ich nuqta)

- `jobs/reminder_job.py` — bitta `app_settings.remind_time` vaqtida ishga
  tushadi, BUGUN muddati bor ACTIVE/STOPPED tasklarni topib bitta bir xil
  xabar yuboradi. Ko'p vaqtli jadval, eskalatsiya darajasi YO'Q.
- `jobs/daily_sync_job.py` — har kuni 01:00 da barcha ochiq kartalarni
  tekshiradi, `trello_sync_service.determine_status()` orqali label rangini
  yangilaydi (6.3-band), yopilgan/arxivlangan kartalarni `COMPLETED` qiladi.
  Bu allaqachon ishlaydi va o'zgarishsiz qoladi.
- `trello_sync_service.determine_status()` — `CardStatus` (label rang uchun,
  `TaskStatus`dan ALOHIDA enum) hisoblaydi, lekin `tasks.status`ga hech qachon
  YOZMAYDI. `TaskStatus.OVERDUE` bazada bor lekin faqat UI-yorliqlarda
  ishlatiladi ("o'lik kod" — hech qachon DB'ga yozilmaydi).
- `timer_service.py` — "Stop" funksiyasi (7.5-band) TO'LIQ ishlaydi: sabab
  majburiy, `stop_logs` jadvaliga yoziladi, `notification_service.notify_task_stopped`
  orqali to'xtatgan xodim + brigadiri + bo'lim SUPERVISOR/ADMIN'lariga signal
  boradi. Taymer "Stop" paytida to'liq to'xtaydimi degan ochiq savol (TZ 19-band,
  savol #6) hali hal qilinmagan — hozircha kechikish `deadline`dan hisoblanadi,
  stop davri ayirilmaydi.
- Trello kartaga real A'ZO biriktirish (6.2-band) — YO'Q. `employees.trello_username`
  faqat matn, Trello API orqali tekshirilmagan/bog'lanmagan.
- Trello checklist (6.2-band) — YO'Q.
- 8.3-band (avto brigadaga o'tkazish) — YO'Q, hech qanday kod izi yo'q.

## A. Ko'p martali eslatma jadvali + eskalatsiya (7.2/7.3-band)

TZ 7.3-band jadvali: 09:00 (1-eslatma), 13:00 (2-eslatma), 15:00 (3-eslatma),
17:00 (oxirgi ogohlantirish), 18:00 (DEDLAYN — shu vaqtdan keyin jarima
boshlanadi). TZ shart qiladi: "eslatma vaqtlari va soni admin paneldagi
SOZLAMALARDAN o'zgartiriladigan bo'lishi SHART" (16-band ham shu talabni
takrorlaydi).

**Qaror**: `app_settings.reminder_schedule` — yangi JSON ustun (yangi jadval
EMAS, chunki bu faqat 4 qatorli kamdan-kam o'zgaruvchi ro'yxat — `penalty_rules`
kabi haqiqiy variable-length jadval kerak emas). Format:
`[{"time": "09:00", "urgency": "info"}, {"time": "13:00", "urgency": "info"},
{"time": "15:00", "urgency": "warning"}, {"time": "17:00", "urgency": "urgent"}]`.
Eski `remind_time` ustuni butunlay olib tashlanadi.

18:00 "DEDLAYN" universal reminder vaqti sifatida QATTIQ KODLANMAYDI — sabab:
real muddatlar `DD.MM.YYYY HH:MM` sifatida turlicha kiritiladi, hammasi
18:00da tugamaydi. Buning o'rniga "muddat o'tdi" hodisasi har bir taskning
o'z `deadline`iga nisbatan HAR SOATDA tekshiriladi (B-qism, `overdue_watch_job`).

### Kerakli o'zgarishlar
- `db/models/app_setting.py`: `reminder_schedule: Mapped[list]` (JSON,
  NOT NULL, migratsiyada `server_default`) — **BAJARILGAN** (model darajasida).
- `utils/enums.py`: `ReminderUrgency(str, Enum)` = INFO/WARNING/URGENT —
  **BAJARILGAN**.
- `services/settings_service.py`: `AppSettingsSnapshot.remind_time` ->
  `reminder_schedule: list[dict]`; `update_setting()` validatsiyasi (vaqtlar
  takrorlanmasin, `urgency` faqat uchta qiymatdan biri bo'lsin) — **QILINMAGAN**.
- `jobs/reminder_job.py`: `run(bot, urgency: ReminderUrgency)` — imzo
  o'zgaradi, xabar matni `urgency`ga qarab kuchayadi (info -> oddiy, warning
  -> "Diqqat, muddat yaqinlashmoqda", urgent -> "Bugun oxirgi muhlat!") —
  **QILINMAGAN**.
- `services/notification_service.py`: `notify_daily_reminder(bot, employee_id,
  tasks, urgency)` — matn shablon tanlovi — **QILINMAGAN**.
- `main.py`: bitta `add_job` o'rniga `reminder_schedule` har bir elementi
  uchun sikl: `scheduler.add_job(reminder_job.run, "cron", hour=.., minute=..,
  args=[bot, urgency], id=f"reminder_job_{i}")` — **QILINMAGAN**.
- `handlers/admin/settings.py`: `remind_time` tahrirlash oqimi o'rniga
  `reminder_schedule` ro'yxatini ko'rsatish + tahrirlash/qo'shish/o'chirish
  (yangi FSM, `DepartmentChainStates` naqshida). Har o'zgarishda mos
  `reminder_job_{i}` scheduler job qayta rejalashtiriladi/qo'shiladi/olib
  tashlanadi — **QILINMAGAN**.

## B. `TaskStatus.OVERDUE`ni bazaga yozish + "1 kun qoldi"/"muddat o'tdi" (7.2-band)

TZ 7.2-band jadvali (bildirishnoma hodisalari):
- "Muddatga 1 kun qoldi" -> Xodim, Brigadir, Nazoratchi.
- "Muddat o'tib ketdi" -> Xodim, Nazoratchi, Rahbar.

Yangi job: `jobs/overdue_watch_job.py`, soatiga bir marta (`cron minute=0`):
1. **"1 kun qoldi"**: `status IN (ACTIVE, STOPPED)`, `deadline` 24 soat ichida,
   `day_left_notified_at IS NULL` -> bildirishnoma (Xodim+Brigadir+Nazoratchi)
   + `day_left_notified_at = now` (qayta yubormaslik uchun).
2. **"Muddat o'tdi"**: `deadline < now` -> `status = OVERDUE` + bildirishnoma
   (Xodim+Nazoratchi+Rahbar/ADMIN).
3. 8.3 tekshiruvi (D-qismga qarang, shu job ichida).

### Kerakli o'zgarishlar
- `db/models/task.py`: `day_left_notified_at: Mapped[Optional[datetime]]` —
  **BAJARILGAN** (model darajasida).
- `db/repositories/task_repo.py`: `list_deadline_approaching()`,
  `list_newly_overdue()` — **QILINMAGAN**.
- `services/notification_service.py`: `notify_deadline_approaching(bot,
  task_id)`, `notify_task_overdue(bot, task_id)` — `notify_task_stopped`dagi
  rol-asosidagi qabul-qiluvchi yig'ish kodini qayta ishlatadi — **QILINMAGAN**.
- `main.py`: `overdue_watch_job.run`ni soatlik cron sifatida ulash —
  **QILINMAGAN**.
- Tekshirish: `daily_sync_job._list_open_tasks()` filtri allaqachon OVERDUE'ni
  o'z ichiga oladi (status not in COMPLETED/PENDING_SETUP) — o'zgarishsiz.
- `_STATUS_LABELS` (`worker/tasks.py`, `keyboards/worker_kb.py`,
  `brigadier/stats.py`) — OVERDUE yorlig'i allaqachon bor, tegilmaydi.

## C. Trello kartaga real a'zo + checklist (6.2-band)

TZ talabi: "Mas'ul xodim(lar) — biriktirilgan a'zolar (ishchi + brigadir +
nachalnik belgilanadi)" va "Checklist — bajarilishi kerak bo'lgan qadamlar".

**Checklist mazmuni** (foydalanuvchi tasdiqlagan): bo'lim zanjiri bo'yicha
avtomatik — har bosqich (`departments.next_department_id` zanjiri) = 1
checklist punkti, bosqich tugaganda (`advance_task_stage()`) shu punkt
avtomatik belgilanadi.

### C.1. Xodim <-> Trello a'zo bog'lanishi
- `db/models/employee.py`: `trello_member_id: Mapped[Optional[str]]` (Trello
  24-xonali hex ID, API chaqiruvlari uchun) — **BAJARILGAN** (model darajasida).
- `trello/client.py`: `get_member_id(username) -> str` (GET
  `/members/{username}`), `add_member_to_card(card_id, member_id)` (POST
  `/cards/{id}/idMembers`), `remove_member_from_card(card_id, member_id)`
  (DELETE `/cards/{id}/idMembers/{member_id}`) — **QILINMAGAN**.
- `handlers/admin/employee_management.py`: xodim yaratish/tahrirlash oqimiga
  "Trello username" qadami; kiritilgan username darhol `get_member_id()`
  bilan tekshiriladi (404 -> "topilmadi, qayta kiriting") — **QILINMAGAN**.
- `services/task_service.py`:
  - `create_task()`: karta yaratilgach, har bir xodim uchun (agar
    `trello_member_id` bo'lsa) `add_member_to_card()`. Xodimning ID'si yo'q
    bo'lsa faqat `logger.warning` (xato tashlanmaydi, ikkinchi-darajali).
  - `advance_task_stage()`: yangi bosqich ochilganda ESKI bosqich xodimlarini
    kartadan olib tashlaydi.
  - `activate_pending_stage()`: yangi bosqich xodimlarini kartaga qo'shadi
    (bu funksiyaga birinchi Trello chaqiruvi, hozir umuman yo'q).
  - Barchasi — **QILINMAGAN**.

### C.2. Bo'lim zanjiri checklist
- `db/models/task.py`: `trello_checklist_id: Mapped[Optional[str]]` —
  **BAJARILGAN** (model darajasida).
- `trello/client.py`: `create_checklist(card_id, name)` (POST `/checklists`),
  `add_checklist_item(checklist_id, name)` (POST
  `/checklists/{id}/checkItems`), `check_checklist_item_by_name(checklist_id,
  item_name)` (GET bilan mos punktni nomi bo'yicha topib, PUT
  `/cards/{cardId}/checkItem/{id}` orqali `state=complete`) — **QILINMAGAN**.
- `services/task_service.py`:
  - `create_task()`: `next_department_id` zanjiri bo'ylab to'liq bo'lim
    ro'yxati yig'iladi, `create_checklist(card_id, "Bosqichlar")` + har bo'lim
    uchun `add_checklist_item()`. Xato bo'lsa faqat log (ikkinchi-darajali).
  - `advance_task_stage()`: `previous_task.trello_checklist_id` yangi qatorga
    ko'chiriladi, eski bosqich nomi `check_checklist_item_by_name()` bilan
    belgilanadi.
  - Barchasi — **QILINMAGAN**.

## D. 8.3-band: uzoq kechikishda avtomatik brigadaga o'tkazish

TZ aniq matni (8.3): "Ba'zi yo'nalishlarda 2 kundan ortiq kechiksa, buyurtma
AVTOMATIK boshqa brigadaga o'tkaziladi. Bu — yo'nalish bo'yicha sozlanadigan
qoida, barcha yo'nalishda majburiy emas... Shu bilan bir vaqtda rahbar rasman
jarimani e'lon qiladi — tizim signal beradi, lekin yakuniy tasdiqni rahbar
qo'lda beradi."

Demak: **avtomatik qism** — aniqlash+signal berish (48 soat+ kechikkanda).
**Qo'lda qism** — rahbar qaysi brigadaga o'tkazishni tanlaydi va tasdiqlaydi
(tizim o'zi brigada tanlamaydi). TZ 19-band ochiq savol #4a: qaysi
yo'nalishlarda bu qoida yoqilganini ANIQ ro'yxat hali yo'q — shu sabab
bo'lim darajasida sozlanadigan boolean qilinadi (har bo'lim uchun admin
o'zi yoqadi/o'chiradi).

### D.1. Bo'lim darajasidagi sozlama
- `db/models/department.py`: `auto_reassign_after_48h: Mapped[bool]`
  (NOT NULL, `server_default=false`) — **BAJARILGAN** (model darajasida).
- `handlers/admin/settings.py`: yangi `/autoreassign` buyrug'i — bo'limlar
  ro'yxati, har birida yoqish/o'chirish inline tugmasi — **QILINMAGAN**.

### D.2. Aniqlash + signal (`overdue_watch_job` ichida, B-qism bilan bir jobda)
- `TaskRepository.list_overdue_for_reassignment_check()`: `status ==
  OVERDUE`, `department.auto_reassign_after_48h == True`, `now - deadline >
  48 soat`, `reassignment_signaled_at IS NULL` — **QILINMAGAN**.
- Har biri uchun: `reassignment_signaled_at = now` + bo'lim rahbari
  (nazoratchi) + barcha ADMIN'larga "Ko'rib chiqish" tugmali signal —
  **QILINMAGAN**.
- `db/models/task.py`: `reassignment_signaled_at: Mapped[Optional[datetime]]`
  — **BAJARILGAN** (model darajasida).

### D.3. Qo'lda tasdiqlash oqimi (yangi handler)
- `states/reassign_task_states.py` (yangi): `waiting_for_brigade`,
  `confirming` — **QILINMAGAN**.
- `handlers/admin/reassign_task.py` (yangi, `RoleAccessMiddleware({ADMIN,
  SUPERVISOR})`): "Ko'rib chiqish" -> shu bo'limdagi BOSHQA brigadalar
  ro'yxati -> tanlash -> tasdiqlash -> `task_service.reassign_task_brigade()`
  -> bildirishnoma — **QILINMAGAN**.
- `main.py`: yangi routerni ulash — **QILINMAGAN**.

### D.4. Ikkiga bo'lingan jarima mantig'i (`task_service.reassign_task_brigade`)

Tasdiqlangan yechim (foydalanuvchi tanlovi): almashtirish paytida ESKI
brigadaga DARHOL jarima, YANGI brigada uchun hisoblash bazasi almashtirish
vaqtidan boshlanadi.

1. Joriy `task_assignments` (eski brigada xodimlari) o'qiladi.
2. **Eski brigadaga darhol jarima**: `hours_late = now - task.deadline`,
   `penalty_service`dagi bracket-topish+KpiLog-yozish mantig'i umumiy
   funksiyaga chiqarilib (`_apply_penalty(task, employee_ids, hours_late,
   reason)` — mavjud `calculate_and_apply_task_penalty` ichidan ko'chiriladi),
   YANGI KpiLog yoziladi. **Task `COMPLETED` qilinmaydi.**
3. **Yangi hisoblash bazasi**: `task.reassigned_at = now` (yangi ustun —
   **BAJARILGAN** model darajasida). `calculate_and_apply_task_penalty()` —
   agar `task.reassigned_at IS NOT NULL` bo'lsa, `hours_late = finished_at -
   reassigned_at` (o'rniga `finished_at - deadline`) — **QILINMAGAN**.
4. `task_assignments`: eski brigada xodimlari o'chiriladi, yangi brigada
   xodimlari (`EmployeeRepository.list_by_brigade()` — yangi metod)
   qo'shiladi — **QILINMAGAN**.
5. Trello: eski brigada a'zolari kartadan olib tashlanadi, yangi brigada
   a'zolari qo'shiladi (C.1dagi metodlar qayta ishlatiladi) — **QILINMAGAN**.
6. `notify_task_reassigned` — eski brigadaga va yangi brigadaga alohida
   xabar — **QILINMAGAN**.

## Migratsiya

Bitta migratsiya (`470b837c8dae_phase2_reminder_schedule_overdue_trello_.py`)
generatsiya qilingan, quyidagi ustunlarni qamrab oladi: `app_settings.
reminder_schedule` (yangi, NOT NULL — **`server_default` YO'Q, TEKSHIRISH
SHART**, aks holda mavjud qatorli jadvalda `alembic upgrade head` yiqiladi),
`app_settings.remind_time` (o'chiriladi), `departments.
auto_reassign_after_48h` (yangi, NOT NULL — **`server_default` YO'Q, TEKSHIRISH
SHART**), `employees.trello_member_id`, `tasks.day_left_notified_at`,
`tasks.reassignment_signaled_at`, `tasks.reassigned_at`,
`tasks.trello_checklist_id` (barchasi nullable, muammosiz).

**KEYINGI QADAM**: migratsiya faylini qo'lda tahrirlab ikkala NOT NULL
ustunga `server_default` qo'shish, keyin `alembic upgrade head` (PowerShell
orqali — bu loyihada Bash emas, PowerShell venv/alembic buyruqlari uchun
tasdiqlangan vosita).

## Tekshirish rejasi (real Railway DB + Trello "Test" board)

Har bir qism (A/B/C/D) alohida `bot/_smoke_phase2_*.py` skript bilan
tekshiriladi (1-bosqichdagi naqshda), ishlatilgach o'chiriladi:

1. **A**: `reminder_schedule` yozish/o'qish; `main.py` sikli to'g'ri sondagi
   `reminder_job_N` job'larini ro'yxatga oladimi (`scheduler.get_jobs()`).
2. **B**: sun'iy o'tmishdagi deadline'li ACTIVE task -> `overdue_watch_job.run()`
   -> `status == OVERDUE`, bildirishnoma xatosiz yuborilgani. Alohida — 23
   soatdan keyin deadline'li task -> "1 kun qoldi" signali + `day_left_
   notified_at` yozilgani.
3. **C**: haqiqiy Trello Test board a'zosi bilan xodim -> `get_member_id()`
   to'g'ri ID -> `create_task()` -> `GET /cards/{id}/members` orqali a'zo
   qo'shilganini tasdiqlash; checklist yaratilgani va bo'lim zanjiri
   punktlari borligini tekshirish; `advance_task_stage()`dan keyin eski
   punkt "complete" bo'lganini tekshirish.
4. **D**: 2 brigada bilan bo'lim, `auto_reassign_after_48h=true`; 49 soat
   kechikkan OVERDUE task -> signal + `reassignment_signaled_at` ->
   `reassign_task_brigade()` qo'lda chaqirib: eski brigadaga KpiLog, `task_
   assignments` almashgani, Trello a'zolar almashgani, `reassigned_at` ->
   `finish_task`+`calculate_and_apply_task_penalty` chaqirib `hours_late`
   `reassigned_at`dan hisoblanganini tasdiqlash.
5. Har qismdan keyin `shared/db-schema.md` mos bo'limi yangilanadi.
6. Barcha `__smoke%` test ma'lumotlari va Trello test kartalari tozalanadi.

To'liq batafsil texnik reja (kod darajasida, funksiya imzolari bilan):
`C:\Users\Acer\.claude\plans\streamed-drifting-pie.md` (global plan fayli,
ExitPlanMode orqali tasdiqlangan).
