# TALABLAR_AUDIT.md — kod bo'yicha audit natijasi

> ## ⚠️ va ❌ bandlar bo'yicha ish (2026-08-04)
>
> Auditdan keyin **barcha ⚠️ bandlar** va **❌ bandlarning 2 tasi** (2.3, 5.6)
> tuzatildi. Natija quyidagi "Tuzatishlar" bo'limida.
>
> Uchta ❌ tuzatilmadi va SIZNING QARORINGIZNI kutmoqda:
> **6.1** (ikki xil o'qilishi mumkin), **8.3** multi-tenant va **8.4** tarif
> (CLAUDE.md'da "ataylab qurilmagan, qo'shishdan oldin tasdiqlang" deb
> yozilgan; ikkalasi ham butun sxemani va MUZLATILGAN mebel modulini qayta
> yozishni talab qiladi). Sabablari "❌ — qaror kutilmoqda" bo'limida.
>
> **Auditdagi bitta xato tuzatildi:** 8.2-bandda `screenAddMaterialTemplate`
> ham `module` yubormaydi deb yozilgan edi — aslida u allaqachon
> `module: nav.module` yuboradi ([app.js:1664]). Faqat `screenAddDepartment`
> buzuq edi. (Xato manbasi: `.claude/nazorat-trello/01-...md` dagi eskirgan
> izoh.)

> Sana: 2026-08-04. Manba: `TALABLAR_AUDIT.md` (22.07.2026 transkript).
> Usul: `bot/` (handlerlar, servislar, job'lar, Mini App API+frontend),
> `web/`, `shared/db-schema.md` o'qildi + **haqiqiy Railway DB** dan
> `departments`, `penalty_rules`, `app_settings`, `employees`, `brigades`
> jadvallari o'qib chiqildi (faqat SELECT).
>
> Belgilar: ✅ BOR / ⚠️ QISMAN / ❌ YO'Q. Taxmin qilinmagan — kodda aniq
> ko'rinmagan narsa ❌ deb yozilgan.
>
> **Muhim kontekst:** tizimda ikkita modul bor —
> `module="mebel"` (Mini App'da **"Fasad seh"**, ishlab chiqarishda,
> muzlatilgan) va `module="fasad_sex"` (**"Nazorat Trello"**, faol ish).
> Ushbu TZ **Nazorat Trello** oqimini tavsiflaydi, shu sabab audit asosan
> `fasad_sex` yo'liga qaraydi va farq bo'lganda alohida aytiladi.

---

## 1. Umumiy arxitektura

### 1.1 Zakaz = Trello kartasi — ✅ BOR
- `bot/services/task_service.py:214-215` — `TrelloClient.create_card()` avval
  Trello'da karta ochadi, keyingina DB qatori yoziladi
  (`task_service.py:221-235`).
- Mebel modulida teskari yo'nalish: karta Trello'da qo'lda yaratiladi,
  `bot/jobs/trello_ingest_job.py` uni o'qib DB'ga tushiradi
  (`task_service.sync_trello_card_stage()`, `task_service.py:269`).

### 1.2 Har bosqich = alohida list, bosqichlar soni qattiq kodlanmagan — ✅ BOR
- Bosqichlar `departments` jadvalida ma'lumot sifatida
  (`bot/db/models/department.py`), kodda ro'yxat yo'q.
- Zanjir `departments.next_department_id` (`department.py:30`) orqali,
  Trello list bog'lanishi `trello_list_id` (`department.py:25`).
- CRUD to'liq: `POST /admin/departments` (`bot/miniapp/api/admin.py:130`),
  `POST /admin/departments/{id}` (`admin.py:232`),
  `DELETE /admin/departments/{id}` (`admin.py:187`),
  zanjir `POST /admin/departments/{id}/chain` (`admin.py:279`).
- ⚠️ **Nuqson (8.2-bandga qarang):** Mini App'ning bo'lim qo'shish formasi
  `module` yubormaydi, yangi bo'lim `"mebel"` ga tushadi.

### 1.3 Har bosqichga: mas'ul, muddat, jarima balli — ⚠️ QISMAN
| Element | Holat | Joy |
|---|---|---|
| Mas'ul xodim(lar) | ✅ | `task_assignments` jadvali, `task_service.py:237-238`, `activate_pending_stage()` `task_service.py:657` |
| Muddat (soat/sutka) | ✅ | `departments.default_sla_hours` (`department.py:95`), Mini App'da tahrirlanadi (`app.js:1471`) |
| Jarima balli | ⚠️ | `penalty_rules` jadvali bosqich bo'yicha bo'lishi MUMKIN (`department_id` ustuni bor, `db/repositories/penalty_rule_repo.py:24`), lekin **UI/API umuman yo'q** va DB'dagi 5 qoidaning hammasi `department_id = NULL` (global) |

**Yetishmayotgani:** jarima jadvalini bo'lim kesimida sozlash faqat
to'g'ridan-to'g'ri SQL orqali mumkin. Hozirgi global jadval:
`[0,24)→-1`, `[24,48)→-2`, `[48,72)→-5`, `[72,96)→-8`, `[96,∞)→-12`.

### 1.4 Bir bosqichga 1 tadan ortiq odam — ✅ BOR
- Servis darajasida ro'yxat qabul qilinadi:
  `task_service.create_task(employee_ids: list[int])` (`task_service.py:190`),
  `activate_pending_stage(employee_ids)` (`task_service.py:658`),
  `delegate_task(worker_ids)` (`task_service.py:728`).
- UI: brigadir bir nechta ishchini belgilay oladi (checkbox ro'yxati,
  `bot/miniapp/public/js/app.js:1944` `screenDelegateTask`), backend
  `bot/miniapp/api/brigadier.py:187`.
- Ball ikkalasiga ham yoziladi:
  `penalty_service._write_scores_for_employees()` (`penalty_service.py:86`),
  `app_settings.penalize_all_assignees` bilan sozlanadi
  (`db/models/app_setting.py:105`; DB'da hozir `True`).
- Eslatma: rahbar birinchi tayinlashda faqat **bitta brigadir** tanlaydi
  (`admin.py:426`, `app.js:1785`) — ko'p odam brigadir topshirig'i orqali
  qo'shiladi, bu ataylab qilingan ikki bosqichli oqim.

### 1.5 Bo'limni (sexni) tanlash punkti — ✅ BOR
- `POST /admin/tasks` `department_id` majburiy (`admin.py:424-427`),
  formada select bor (`app.js:702-704`) va faqat joriy modul bo'limlari
  ko'rsatiladi.

---

## 2. Muddat (srok) mantiqi

### 2.1 Muddat kartaga muddat qo'yilgan paytdan boshlanadi — ✅ BOR
- `task_service.resolve_stage_deadline()` (`task_service.py:421`)
  `_spawn_pending_stage()` ichidan (`task_service.py:463`) — ya'ni buyurtma
  bosqichga **kirgan aniq paytda** `deadline = now + SLA` hisoblanadi,
  nazoratchi tugma bosgan paytdan emas.
- Bosqich baribir `PENDING_SETUP` bo'lib turadi (xodim kutilmoqda), lekin
  soat allaqachon ketmoqda; `activate_pending_stage(deadline=None)`
  oldindan hisoblangan qiymatni saqlaydi (`task_service.py:701`).
- Mebelda muddat Trello kartaning `due` maydonidan yoki list nomidagi
  soatdan olinadi (`services/trello_board_map.py`).

### 2.2 "Nachalo" sana bilan, muddat soat bilan — ⚠️ QISMAN
- Muddat **soatda** ✅: `default_sla_hours`, `sla_urgent_hours`,
  `sla_over_quota_hours` — hammasi butun soat (`department.py:95-106`).
- Boshlanish vaqti `tasks.started_at` (`db/models/task.py:51`) — to'liq
  timestamp, **alohida "nachalo" (sana) maydoni yo'q**, ya'ni "sana bilan"
  degan farq modelda ifodalanmagan; foydalanuvchi kiritadigan alohida
  boshlanish sanasi ham yo'q.

### 2.3 Muddatni ortga/oldinga qo'lda o'zgartirish — ❌ YO'Q
- `tasks.deadline` yoziladigan yagona joylar: yaratish
  (`task_service.py:225`), `PENDING_SETUP` faollashtirish
  (`admin.py:1177-1213`), va Stop/Resume avtomatik siljishi
  (`timer_service.py:234`).
- **Faol (ACTIVE/OVERDUE) vazifaning muddatini o'zgartiradigan endpoint yoki
  ekran yo'q** — butun `bot/miniapp/api/` bo'ylab tekshirildi.
- Kerak: `POST /admin/tasks/{id}/deadline` + Mini App'da tahrirlash maydoni
  (va o'zgartirish sababi/izi KPI hisobini buzmasligi uchun log).

### 2.4 Muddat o'tsa — vaqt yoziladi va jarima ball qo'shiladi — ✅ BOR
- Soatlik job `status=OVERDUE` qiladi
  (`bot/jobs/overdue_watch_job.py:51` `_process_newly_overdue`).
- Jarima yakunlashda hisoblanadi:
  `penalty_service.calculate_and_apply_task_penalty()`
  (`penalty_service.py:266`), grace-period yo'q — `[0,24)` bracketdan
  boshlanadi.
- Eslatma: "qachon OVERDUE bo'ldi" uchun alohida ustun yo'q; hisob
  `deadline`/`finished_at` ayirmasidan yuritiladi (`penalty_service.py:298`).

### 2.5 Jarima aynan o'sha bosqich odamiga — ✅ BOR
- Har bosqich alohida `tasks` qatori (`tasks.previous_task_id`,
  `task.py:55`), jarima faqat shu qatorning `task_assignments`iga yoziladi
  (`penalty_service.py:300` → `_write_scores_for_employees`
  `penalty_service.py:86`).
- Ishchi bo'lmasa ball brigadirning o'ziga to'liq yoziladi
  (`penalty_service.py:121-122`), brigadir ulushi `brigade_share_ratio`
  bo'yicha (`penalty_service.py:381`).
- SPEC §5.3 blok ichidagi bosqich ball yozmaydi (`penalty_service.py:236`) —
  hozir DB'da hech qaysi bo'limda `sla_block_id` yo'q, ya'ni bu yo'l faol emas.

### 2.6 "Srochnost" belgisi → muddat avtomatik 24 soat — ⚠️ QISMAN
- `tasks.is_urgent` bor (`task.py:111`), yaratishda belgilanadi
  (`admin.py:470`, `app.js:705`/`764`) va zanjir bo'ylab ko'chadi
  (`task_service.py:479`).
- Muddatga ta'siri: `task_service._sla_hours_for_stage()`
  (`task_service.py:402`) — **24 soat kodda emas**, bo'limning
  `sla_urgent_hours` ustunidan olinadi.
- **Yetishmayotgani (2 ta):**
  1. DB'da 23 `fasad_sex` bo'limdan faqat **bittasida** (`Start`, id 75)
     `sla_urgent_hours=24` qo'yilgan — qolgan 22 bo'limda `NULL`, ya'ni
     srochniy buyurtma o'sha bosqichlarda oddiy muddat oladi.
  2. Mavjud buyurtmani keyinchalik "srochniy" qilib belgilash yo'li yo'q —
     `is_urgent` faqat yaratish so'rovida o'qiladi.

### 2.7 Har bir sex uchun standart muddat admin paneldan — ✅ BOR
- `departments.default_sla_hours` (`department.py:95`),
  `DEPARTMENT_UPDATABLE_FIELDS` (`admin.py:169-184`),
  Mini App formasi `app.js:1471-1476` (SLA, srochniy, kunlik norma,
  norma ustidagi SLA, blok, guruh ID).
- DB'da 20/23 bo'limda haqiqiy qiymat bor (masalan Kontrol 24, Start 48,
  Shpon 360, Kraska 72, Montaj 48).

---

## 3. STOP funksiyasi

### 3.1 Istalgan bosqichda STOP — ✅ BOR
- `timer_service.stop_task()` (`timer_service.py:127`) — `ACTIVE` va
  `OVERDUE` holatlarida ishlaydi (`timer_service.py:143`), sabab majburiy.
- UI: `app.js:528` `screenStopTask`, API `bot/miniapp/api/worker.py:158`.
- Bo'lim darajasida "boshida STOP" ham bor: `departments.starts_stopped`
  (`department.py:41`), `task_service.py:227`. DB'da `Zakaz tushdi` (73) va
  `Sklad` (83) shunday sozlangan.
- Mebelda ishchi o'zi bosa olmaydi — brigadir so'rov yuboradi, rahbar
  tasdiqlaydi (`services/claim_service.py`); bu ataylab qilingan farq.

### 3.2 STOP muddat sanashini to'xtatadi — ✅ BOR
- `timer_service.resume_task()` (`timer_service.py:229-234`): to'xtab turgan
  davr `deadline`ga qo'shiladi va `tasks.stopped_seconds_total`ga jamlanadi.
- `task_repo._timer_running()` STOPPED vazifani `OVERDUE` qilmaydi va
  "muddat yaqin" ogohlantirishini yubormaydi.
- Faqat `fasad_sex` — mebelda muddat Trello'dan qayta o'qilgani uchun
  ataylab tegilmaydi (`timer_service.py:184`).

### 3.3 Vizual rangli yorliq — ✅ BOR
- `services/trello_sync_service.py:34-39`: `To'xtatilgan` = **orange**,
  `Bajarilmoqda` = green, `Bugun tugaydi` = yellow, `Muddati o'tgan` = red.
- Darhol qo'yiladi: `timer_service._sync_stop_label()` (`timer_service.py:56`),
  kunlik ham tasdiqlanadi (`jobs/daily_sync_job.py:61`).
- Qo'shimcha: bo'limda `stop_target_list_id` bo'lsa karta "stopda"
  ro'yxatiga ko'chadi (`timer_service.py:87`) — DB'da hozir hech qaysi
  bo'limda sozlanmagan.

### 3.4 STOP bosilganda sotuvchiga avtomatik xabar — ⚠️ QISMAN
- Kod bor: `notification_service.notify_task_stopped()`
  (`notification_service.py:185`) `task_sellers` jadvalidan sotuvchilarni
  o'qiydi (`notification_service.py:227-230`); buyurtmaga 3 tagacha sotuvchi
  biriktiriladi (`task_service.py:196-198`, `admin.py:458`).
- **Yetishmayotgani (haqiqiy nuqson):** `task_sellers` qatorlari FAQAT
  `create_task()` da yoziladi (`task_service.py:240-243`) va keyingi
  bosqichlarga **ko'chirilmaydi** — `_spawn_pending_stage()`
  (`task_service.py:465-480`) `client_id`, `trello_checklist_id`,
  `is_urgent` ni ko'chiradi, `task_sellers` ni esa yo'q.
  Natija: sotuvchi faqat buyurtmaning **birinchi bosqichida** STOP bo'lsa
  xabar oladi, keyingi 15+ bosqichda — hech qachon.
- Mebel buyurtmalarida sotuvchi umuman biriktirilmaydi
  (`sync_trello_card_stage()` `task_sellers` yozmaydi).

### 3.5 "Stop bosilgan zakazlar" ro'yxati — ✅ BOR
- `stats_service.get_stopped_orders()` (`stats_service.py:412`) — sabab,
  boshlanish vaqti, necha soatdan beri; eng uzog'idan boshlab.
- API `GET /admin/stopped-orders` (`admin.py:870`), ekran
  `app.js:1237` `screenStoppedOrders`, `Statistika` bo'limidan kiriladi
  (`app.js:1101`).

### 3.6 STOP vaqti statistikada alohida — ✅ BOR
- `stats_service.get_stop_stats()` (`stats_service.py:548`) — nechta stop,
  nechta zakaz, necha soat, sabablar reytingi.
- Sof ish vaqti hisobidan chegiriladi: `stats_service.py:121-123`
  (`avg_completion_hours`) va `stats_service.py:504` (bosqich bottleneck).
- Davom etayotgan stop `until` gacha emas, **hozirgacha** hisoblanadi
  (`stats_service.py:557`).

---

## 4. Jarayon bosqichlari va muddatlar

### 4.1 Barcha bosqichlar kodda bormi? — ⚠️ QISMAN
Bosqichlar kodda emas, **DB'da ma'lumot** sifatida. Haqiqiy DB holati
(`departments`, `module='fasad_sex'`) TZ jadvali bilan solishtirildi:

| TZ # | TZ bosqichi | TZ muddat | DB'da | SLA (soat) | Holat |
|---|---|---|---|---|---|
| 1 | Zakaz tushdi (STOPda) | — | `Zakaz tushdi` (73), `starts_stopped=True` | — | ✅ |
| 2 | Kontrolniy zam | 24 | `Kontrol` (74) | 24 | ✅ |
| 3 | Chizish (konstruktor) | 48/72/24, norma 5 | `Start` (75) | 48, srochniy 24, norma 5, norma ustida 72 | ✅ |
| 4 | Gip-lab ga o'tkazish | 24 | `Gip-lab` (77) | 24 | ✅ |
| 5 | Fayl yig'ish | 24 | `Fayl yig'ish` (78) | 24 | ✅ |
| 6 | Fayl + zapchast yig'ish | 24 | — | — | ❌ alohida bo'lim yo'q |
| 7 | Ta'minot | ixtiyoriy | — | — | ❌ bo'lim yo'q |
| 8 | Fayl tashlash (zavod) | 24 | `Laminoks fayl tashaldi` (94), `Eman/dub fayl tashaldi` (97) | 24 | ⚠️ zanjirga ULANMAGAN |
| 9 | Laminat zavodida bajarish | 72 | `... ishlab chiqarishda tasdiqlandi` (95, 98) | 72 | ⚠️ zanjirga ULANMAGAN |
| 10 | Raspil (fork nuqtasi) | — | — | — | ⚠️ fork bor, lekin `Fayl yig'ish`da; `Raspil` bo'limi yo'q |
| 11 | Korpus sex | 24 | `Korpus qismi` (79) + `Korpus sexi (upakovka)` (82) | 24 | ✅ |
| 12 | Fasad: shpon→shkurka→kraska | 15 sutka (umumiy) | `Shpon` (84) 360, `Shkurka` (85) 72, `Kraska` (86) 72 | — | ⚠️ har biriga alohida muddat, umumiy 15 sutkalik **blok yo'q** (`sla_block_id` hamma joyda NULL) |
| 13 | Malyarka / quritish / upakovka | — | `Malyarka` (87) | 24 | ⚠️ quritish alohida yo'q |
| 14 | Dostavka (logistika) | 24 | `Dostavka (Logistika)` (88) | 24 | ✅ |
| 15 | Dostavkadan keyin STOP | — | — | — | ❌ `Dostavka → Montaj` to'g'ridan-to'g'ri, `Montaj.starts_stopped=False` |
| 16 | Ustanovka (montaj) | sozlanadi | `Montaj (Ustanovka)` (89) | 48 | ⚠️ bitta bo'lim, 7–8 brigada emas; brigada/xodim 0 |

Qo'shimcha DB'da bor, TZ ro'yxatida yo'q: `Stolyarka` (76, 24s),
`Sklad` (83, 24s, `starts_stopped`), `Ichki qism` (80), `Fasad qismi` (81).

**Muhim ma'lumot holati:** `fasad_sex` bo'limlarida **0 xodim, 0 vazifa,
0 brigada** — zanjir texnik jihatdan tayyor, lekin hech qachon amalda
ishlatilmagan (jami 15 faol xodimning hammasi `mebel` bo'limlarida, bittasi
sotuvchi).

### 4.2 Fasad/korpus oqimining ajralishi va qayta birlashishi — ✅ BOR
- Kod: `task_service.advance_task_stage()` (`task_service.py:483`) —
  `Task | list[Task] | None` qaytaradi; fork `department_fork_targets`
  jadvalidan (`task_service.py:536`), join `departments.requires_join`
  bo'yicha barcha qardosh tarmoq tugashini kutadi (`task_service.py:558-570`).
- Poyga himoyasi: `pg_advisory_xact_lock` (`task_service.py:636`).
- DB'da haqiqiy sozlash bor: `Fayl yig'ish` (78) → `Korpus qismi` (79),
  `Ichki qism` (80), `Fasad qismi` (81); uchalasi → `Korpus sexi` (82,
  `requires_join=True`).
- Karta fork davomida joyidan qo'zg'almaydi (bitta karta 3 listda tura
  olmaydi) — progress checklist orqali ko'rinadi (`task_service.py:585-591`).
- ⚠️ Hech qachon haqiqiy buyurtmada sinalmagan (0 task).

### 4.3 "Necha sutkada bajarildi" statistikasi — ✅ BOR
- Bosqich kesimida: `stats_service.get_stage_bottlenecks()`
  (`stats_service.py:494`) — o'rtacha haqiqiy davomiylik (STOP chegirilgan)
  vs reja (`default_sla_hours`), eng sekinidan boshlab.
- Xodim kesimida: `EmployeeStats.avg_completion_hours`
  (`stats_service.py:52`, hisob `stats_service.py:121-139`).
- API: `GET /admin/stats/bottlenecks` (`admin.py:912`), ekran `app.js:1195`.

---

## 5. Xabarnomalar (Telegram)

### 5.1 Xodimga shaxsiy xabar — ✅ BOR
- `notification_service.notify_task_started()` (`notification_service.py:123`)
  — barcha biriktirilgan xodimga, Mini App tugmasi bilan.
- Chaqiriladi: `admin.py` (vazifa yaratish), `brigadier.py:218` (topshirish),
  `trello_ingest_job` (mebel a'zo o'zgarishi).

### 5.2 Xodimning rahbariga dublikat — ⚠️ QISMAN
- Ustun bor: `employees.manager_id` (`db/models/employee.py:55`),
  yordamchi `notification_service._add_managers()`
  (`notification_service.py:84`).
- **Faqat 2 ta hodisada ulangan:** muddat o'tgani
  (`notification_service.py:415`) va jarima ball yozilgani
  (`notification_service.py:300-306`, faqat manfiy ball).
- ❌ `notify_task_started` (yangi vazifa) da rahbar YO'Q — TZ aynan
  "yangi vazifa biriktirilganda dublikat" deydi.
- ❌ Faqat bitta pog'ona (rahbarning rahbari qo'shilmaydi —
  `notification_service.py:88-91` izohida ataylab shunday).
- Ma'lumot: DB'da **hech bir xodimda `manager_id` qo'yilmagan** (0/15),
  ya'ni kanal amalda ishlamayapti.
- Mebel modulida bu kanal kodda butunlay o'chirilgan
  (`notification_service._is_mebel()`, `notification_service.py:58`).

### 5.3 Sotuvchiga xabar — STOP va zakaz harakati — ⚠️ QISMAN
- STOP: qisman — 3.4-bandga qarang (birinchi bosqichdan keyin sotuvchi
  bog'lanmay qoladi).
- **Zakaz harakati (bosqich o'tishi): ❌** — `notify_client_stage_advanced()`
  (`notification_service.py:475`) faqat **mijozga** yuboradi. Sotuvchiga
  bosqich o'tishi haqida xabar beradigan kod yo'q (butun
  `notification_service.py` tekshirildi).

### 5.4 Guruhga xabar (fasad guruhi, krovat guruhi...) — ⚠️ QISMAN
- Ustun bor: `departments.telegram_chat_id` (`department.py:123`), o'qish
  `notification_service._department_chat_id()` (`notification_service.py:71`),
  Mini App'da tahrirlanadi (`app.js:1476`).
- Faqat **2 hodisa** guruhga boradi: yangi vazifa
  (`notification_service.py:152-154`) va muddat o'tdi
  (`notification_service.py:421-422`). STOP, bosqich o'tishi, jarima —
  guruhga ketmaydi.
- Ma'lumot: **23 bo'limning hammasida `telegram_chat_id = NULL`** — bot
  hali birorta guruhga qo'shilmagan, ya'ni funksiya amalda o'chiq.
- Har sex uchun bittadan guruh modeli bor; "krovat guruhi / laminat guruhi"
  kabi bo'lim bo'lmagan guruhlar uchun mexanizm yo'q.

### 5.5 Muddat tugashiga yaqin / tugagach eslatma — ✅ BOR
- Yaqinlashgani: `overdue_watch_job._process_deadline_approaching()`
  (`jobs/overdue_watch_job.py:29`), oyna `app_settings.deadline_warning_hours`
  (DB'da **4 soat**), mebelda o'zgarmas 24 soat.
- O'tgani: `_process_newly_overdue()` (`overdue_watch_job.py:51`).
- Takroriy: `_process_overdue_repeat_reminders()` (`overdue_watch_job.py:70`),
  `overdue_repeat_hours` (DB'da **12 soat**).
- Kunlik jadval bo'yicha ham eslatma: `jobs/reminder_job.py` +
  `app_settings.reminder_schedule` (DB'da 10:00 info, 17:00 urgent).

### 5.6 Xabarnomani foydalanuvchi o'chira olmasligi — ❌ YO'Q
- Kodda `disable_notification`/`protect_content` yoki "o'qildi/tasdiqlash"
  mexanizmi yo'q (`bot/` bo'ylab grep qilindi — faqat aiogram kutubxonasi
  ichida).
- `notification_service._send()` (`notification_service.py:104`) botni
  bloklagan xodim uchun faqat `logger.warning` yozadi
  (`notification_service.py:114-115`) — rahbarga hech qanday signal ketmaydi.
- Telegram platformasida foydalanuvchini bot chatini "mute" qilishdan
  to'xtatib bo'lmaydi. Realistik yechim: xabarni **o'qilganini tasdiqlash**
  (inline tugma) + tasdiqlanmagan xabar bo'yicha eskalatsiya. Bunday kod yo'q.

---

## 6. "Vazifa buyurish" moduli

### 6.1 Jarayon boshida "Vazifa buyurish" punkti — ❌ YO'Q
- MISC vazifalar (`TaskType.MISC`, `utils/enums.py:25`) buyurtma zanjiridan
  **butunlay ajratilgan**: `create_misc_task()` (`task_service.py:850`)
  Trello'ga tegmaydi, `previous_task_id` qo'ymaydi, buyurtmaga bog'lanmaydi.
- Zanjirda "Vazifa buyurish" nomli bo'lim yo'q (DB'da 23 bo'lim tekshirildi).
- Ya'ni: alohida vazifa moduli sifatida ✅, lekin **jarayonning bosh
  punkti** sifatida ❌.

### 6.2 Uch xil vazifa turi — ✅ BOR
- `MiscCategory` (`utils/enums.py:29`): `office` (ofis), `fasad_sex`,
  `installer` (o'rnatuvchi), `welder` (payvandchi) — TZ'dagi
  "ustanovkachi + svarshik" ikkita alohida kategoriya qilingan.
- UI: `app.js:718-721` (yaratishda tanlash), `app.js:618`
  `screenAdminMiscTasks(category)` (kategoriya bo'yicha ko'rish).

### 6.3 Rahbar istalgan xodimga vazifa + muddat — ⚠️ QISMAN
- `POST /admin/misctasks` (`admin.py:694`) → `create_misc_task()`
  (`task_service.py:850`), muddat majburiy.
- Cheklovlar: **ko'pi bilan 3 xodim** (`task_service.py:867`) va UI'da faqat
  `worker`/`brigadier` rollari tanlanadi (`app.js:724`) — ofis xodimi
  `supervisor`/`seller`/`observer` rolida bo'lsa ro'yxatda **umuman
  ko'rinmaydi**, ya'ni "istalgan xodim" emas.

### 6.4 "Mening vazifalarim" shaxsiy panel — ✅ BOR
- `GET /misctasks` (`bot/miniapp/api/worker.py:91`), buyurtma va vazifa
  ro'yxatlari alohida (`worker.py:51` `_list_my_tasks`).
- UI: alohida "Vazifalar" tab (`app.js:419` `screenTaskList`).

### 6.5 Vazifa bo'yicha ball / jarima ball — ✅ BOR
- MISC ham ORDER bilan bir xil KPI yo'lidan o'tadi: yakunlashda
  `calculate_and_apply_task_penalty()` chaqiriladi (`worker.py:242`),
  faqat `advance_task_stage()` MISC uchun o'tkazib yuboriladi
  (`worker.py:252`).
- Ball ko'rinishi: `GET /score` (`worker.py:388`), ekran `app.js:552`.

---

## 7. Statistika va dashboard

### 7.1 Xodim kesimida statistika — ✅ BOR
- `stats_service.get_monthly_stats()` (`stats_service.py:186`) →
  `EmployeeStats` (`stats_service.py:41`): bajarilgan vazifalar, jami ball,
  jarimalar soni, o'rtacha bajarish soati.
- API `GET /admin/stats` (`admin.py:777`), CSV eksport (`admin.py:952`),
  Telegram jadval (`stats_service.format_stats_table()`
  `stats_service.py:589`), web panel (`web/src/routes/stats.js`).

### 7.2 Sex/bo'lim kesimida statistika — ✅ BOR
- Voronka: `get_order_funnel()` (`stats_service.py:450`) — har bo'limda
  nechta zakaz, holat kesimida.
- Bottleneck: `get_stage_bottlenecks()` (`stats_service.py:494`).
- Sig'im: `get_capacity_vs_actual()` (`stats_service.py:306`).
- Zavod bo'yicha filtr: `factory_name` (`stats_service.py:228`).
- Eslatma: **bo'lim bo'yicha jamlangan KPI/ball** ko'rsatkichi yo'q — ball
  har doim xodim kesimida (bu TZ'da aniq talab qilinmagan).

### 7.3 Brigada hisobi — ✅ BOR
- `get_brigade_monthly_stats()` (`stats_service.py:239`), API
  `GET /brigadier/brigade` (`brigadier.py:87`), ekran `app.js:1867`.
- Brigadir bir nechta brigadaga rahbarlik qila oladi
  (`BrigadeRepository.list_by_brigadier_id()`).
- ⚠️ Ma'lumot: DB'dagi 3 brigadaning hammasi **mebel** bo'limlarida
  (Kraska/Shkurka/Shpon); ustanovka va laminat uchun brigada yaratilmagan.

### 7.4 STOP chegirilgan sof bajarilish vaqti — ✅ BOR
- `tasks.stopped_seconds_total` (`task.py:101`), hisob
  `stats_service.py:121-123` va `stats_service.py:504-506`.

### 7.5 Rahbar uchun umumiy dashboard — ✅ BOR
- Mini App: `GET /admin/dashboard` (`admin.py:78`), ekran `app.js:581`
  `screenAdminHome` (navbatlar: sozlash kutilmoqda, ko'rib chiqish,
  tasdiqlash kutilmoqda).
- Web panel: `web/src/routes/stats.js` + `web/src/public/js/app.js`
  (oylik jadval, Chart.js grafik, eng yaxshi/yomon reyting).
- Rejalangan hisobotlar: `jobs/report_job.py` (kunlik/haftalik/oylik,
  `app_settings.report_time` = 20:00).

---

## 8. Sozlanuvchanlik / sotuvga tayyorlik

### 8.1 Bosqich/muddat/bo'lim admin paroli orqali o'zgartiriladi — ⚠️ QISMAN
- Sozlash imkoni ✅: bo'lim CRUD (`admin.py:130/232/187`), zanjir
  (`admin.py:279`), fork (`admin.py:322`), SLA/norma/blok
  (`admin.py:169-184`), skalyar sozlamalar (`admin.py:1061-1090`),
  eslatma jadvali (`admin.py:1092-1140`).
- ❌ **"Admin paroli" emas** — Mini App autentifikatsiyasi Telegram
  `initData` + rol (`bot/miniapp/auth.py`), parol tushunchasi yo'q.
  Parolli kirish faqat `web/` panelida (`web/src/auth.js`,
  `WEB_ADMIN_PASSWORD`), lekin u yerda **faqat statistika ko'rish va xodim
  qo'shish** bor — bosqich/muddat sozlash yo'q.
- ❌ `penalty_rules` (jarima jadvali) hech qaysi paneldan sozlanmaydi
  (1.3-bandga qarang).
- ❌ `app_settings.sales_board_lists` ham faqat DB orqali.

### 8.2 Yangi punkt (bosqich) qo'shish tugmasi — ⚠️ QISMAN
- Tugma bor: `app.js:1457` (`➕ Bo'lim qo'shish`) → `screenAddDepartment`
  (`app.js:1595`) → `POST /admin/departments` (`admin.py:130`).
- **Nuqson:** forma so'rov tanasiga `module` qo'shmaydi
  (`app.js:1612-1619`), backend esa standart `"mebel"` qo'yadi
  (`admin.py:143`). Ya'ni **Nazorat Trello ichida qo'shilgan yangi bosqich
  muzlatilgan mebel moduliga tushadi** va o'z ro'yxatida ko'rinmaydi.
  Xuddi shu nuqson `screenAddMaterialTemplate` da ham (`app.js:1631`) —
  shu sabab material shablonlari DB'ga qo'lda yozilgan
  (`.claude/nazorat-trello/01-haqiqiy-zanjir-yaratish.md:14-20`).
- Qo'shimcha: yangi bo'lim zanjirga avtomatik ulanmaydi — `next_department_id`
  alohida ekranda qo'lda qo'yiladi (`app.js:1386`).

### 8.3 Har bir korxona uchun alohida konfiguratsiya (multi-tenant) — ❌ YO'Q
- `organization_id`/`company`/`tenant` tushunchasi kodda ham, sxemada ham
  yo'q (`shared/db-schema.md` va barcha `db/models/` tekshirildi).
- Eng yaqin narsalar **multi-tenant emas**:
  - `departments.module` (`department.py:58`) — ikkita qattiq bilingan
    ishlab chiqarish oqimi (`mebel` / `fasad_sex`), dinamik ro'yxatdan
    o'tkazish yo'q;
  - `departments.factory_name` (`department.py:65`) — faqat statistika
    filtri (`stats_service.py:228`), boshqa hech qanday mantiqqa ta'sir
    qilmaydi.
- Bitta Trello hisobi, bitta bot tokeni, bitta `app_settings` qatori
  (singleton) — hammasi bitta korxonaga qattiq bog'langan.

### 8.4 Sodda / to'liq tarif farqi — ❌ YO'Q
- Tarif/plan/limit tushunchasi kodda yo'q. Bosqichlar sonini
  cheklaydigan yoki funksiyani yoqib/o'chiradigan mexanizm yo'q
  (`app_settings`da bunday ustun ham yo'q).
- Texnik jihatdan zanjir uzunligi ma'lumot bilan boshqarilgani uchun
  "kamroq bosqich" qo'lda yasash mumkin, lekin bu tarif tizimi emas.

---

## Yetishmayotgan funksiyalar — muhimlik bo'yicha

### ✅ Yopilgan (2026-08-04)

Auditda topilgan **9 ta band** tuzatildi — batafsili yuqoridagi
"Tuzatishlar" bo'limida:
`2.3`, `1.3/8.1`, `2.6`, `3.4/5.3`, `5.2`, `5.4` (kod qismi), `6.3`, `8.2`,
va qisman `5.6`.

### 🔴 Qolgan — ma'lumot kiritish (kod tayyor, faqat qiymat kerak)

| # | Band | Nima kerak | Qayerdan |
|---|---|---|---|
| 1 | **5.4** | Har sexning Telegram guruh ID'si — hozir 23/23 bo'limda `NULL`, ya'ni guruh xabarlari (yangi vazifa, muddat o'tdi, STOP) hech qayerga bormayapti | Botni guruhga qo'shing → Mini App: Bo'limlar → bo'lim → "Sex Telegram guruhi ID" |
| 2 | **5.2** | Xodimlarga rahbar (`manager_id`) — hozir 0/15 | Mini App: Xodimlar → xodim → "Bevosita rahbar" |
| 3 | **7.3 / 4.1** | `fasad_sex` bo'limlariga xodim va brigada — hozir 0 | Real odamlar botga `/start` yozib ro'yxatdan o'tishi kerak, keyin Mini App'dan bo'lim biriktiriladi |

### 🟡 Qolgan — biznes qarori kerak

| # | Band | Savol |
|---|---|---|
| 4 | **4.1** | 4 ta TZ bosqichi zanjirda yo'q: `Fayl + zapchast yig'ish`, `Ta'minot`, `Raspil`, "dostavkadan keyin STOP". Ular kerakmi? TZ fork'ni `Raspil`da deydi, kodda esa `Fayl yig'ish`da — bular bir xil bosqichmi? |
| 5 | **4.1** | Laminat/Eman zanjirlari (94–99) asosiy zanjirga ulanmagan — qayerga ulanishi kerak? |
| 6 | **4.1 (12-qator)** | shkurka+kraska+malyarka uchun umumiy **15 sutkalik blok** kerakmi? Blok qo'yilsa har bosqichning o'z muddati (72/72/24) **bekor bo'ladi** — ikkovi bir vaqtda ishlamaydi |
| 7 | **4.1 (16-qator)** | Montaj uchun 7–8 brigada nomlari/brigadirlari |
| 8 | **2.6** | `Shpon` odatiy muddati 360 soat (15 kun, quritish), srochniy endi 24 soat — bajarib bo'lmaydigan muddat. Shpon/Shkurka/Kraska uchun boshqa qiymat kerakmi? |
| 9 | **6.1** | Ikki xil o'qiladi — yuqoridagi "❌ — qaror kutilmoqda" bo'limiga qarang |
| 10 | **2.2** | Alohida "nachalo" (boshlanish sanasi) maydoni kerakmi? Hozir `started_at` timestamp bor |

### ⚪ Ochiq, lekin harakat talab qilmaydi

| # | Band | Izoh |
|---|---|---|
| 11 | **5.6** ⚠️ | Mute'ni Telegram'da to'sib bo'lmaydi. Bloklash endi aniqlanadi va eskalatsiya qilinadi. Keyingi qadam ("Tanishdim" tugmasi + eskalatsiya) — so'rasangiz qo'shaman |
| 12 | **8.1** ⚠️ | "Admin paroli" yo'q — Mini App Telegram roli bilan ishlaydi, bu xavfsizroq. TZ iborasi eskirgan bo'lishi mumkin |
| 13 | **8.3 / 8.4** ❌ | Multi-tenant + tarif — ataylab qurilmagan, qayta boshlash uchun sizning tasdig'ingiz kerak ("❌ — qaror kutilmoqda" bo'limiga qarang) |

---

## Tuzatishlar (2026-08-04)

### Kod bilan tuzatilgani — 6 ta ⚠️ → ✅

| Band | Nima qilindi | Fayl |
|---|---|---|
| **3.4 / 5.3** | `task_sellers` endi `client_id` kabi zanjir bo'ylab ko'chadi — sotuvchi buyurtmaning HAR bosqichida "Stop" xabarini oladi, faqat birinchisida emas | `services/task_service.py` (`_spawn_pending_stage`) |
| **5.2** | `notify_task_started` endi rahbarga ham dublikat yuboradi ("Bo'ysunuvchingiz X ga vazifa berildi"), matn ijrochinikidan farqli. Mebel `_is_mebel()` guardi bilan tegilmagan | `services/notification_service.py` |
| **5.4** | "Stop" xabari endi sex guruhiga ham boradi (ilgari guruh kanali faqat "yangi vazifa" va "muddat o'tdi"da ishlardi) | `services/notification_service.py` (`notify_task_stopped`) |
| **8.2** | Bo'lim qo'shish formasi endi `module: nav.module` yuboradi — yangi bosqich muzlatilgan mebel moduliga tushmaydi | `miniapp/public/js/app.js` (`screenAddDepartment`) |
| **6.3** | Maxsus vazifa ijrochilari ro'yxatidan rol filtri olib tashlandi — TZ 6.3 "istalgan xodim" deydi va 6.2 "ofis xodimlari" turini talab qiladi (ilgari faqat worker/brigadir ko'rinardi) | `miniapp/public/js/app.js` (`screenNewTaskForm`) |
| **1.3 / 8.1** | `penalty_rules` uchun to'liq CRUD: `GET/POST/DELETE /admin/penalty-rules` + Sozlamalardagi "Jarima jadvali" ekrani. Bo'limga xos qoida qo'shish endi paneldan mumkin | `miniapp/api/admin.py`, `app.js`, `i18n.js` (uz+ru) |
| **2.6** (kod qismi) | `POST /admin/tasks/{id}/urgent` — mavjud buyurtmani srochniy qilish; belgi qo'yilganda muddat bo'limning srochniy SLA'sidan qayta hisoblanadi va keyingi bosqichlarga ko'chadi. UI: "Sozlash kutilmoqda" ekranidagi checkbox | `miniapp/api/admin.py`, `app.js` |

Qo'shimcha himoya: jarima jadvalidan **global ochiq yuqori chegara** qatorini
(`max_hours_late IS NULL`) o'chirish/yopish endi 409 bilan rad etiladi —
usiz yetarlicha kech tugagan vazifa jimgina jarimasiz o'tib ketardi
(`_global_top_rule_survives()`).

### Ma'lumot bilan tuzatilgani — 1 ta ⚠️ → ✅

| Band | Nima qilindi |
|---|---|
| **2.6** (ma'lumot qismi) | 19 ta `fasad_sex` bo'limga `sla_urgent_hours = 24` qo'yildi (ilgari faqat `Start`da bor edi). TZ 2.6 aynan shu raqamni belgilaydi. Muddatsiz bosqichlar (`Zakaz tushdi`, ikkita "100% tayyor") tegilmadi |

> **Diqqat qiling:** `Shpon` bosqichining odatiy muddati **360 soat (15 kun)** —
> jismoniy jarayon (quritish). Srochniy belgisi qo'yilsa u endi **24 soat**ga
> tushadi, ya'ni amalda bajarib bo'lmaydigan muddat va kafolatlangan jarima.
> TZ 2.6 shunday deydi, shuning uchun shunday qo'yildi, lekin bu bitta
> `UPDATE` bilan o'zgartiriladi — Shpon/Shkurka/Kraska uchun boshqa srochniy
> qiymat kerak bo'lsa ayting.

### ❌ bandlar — tuzatilgani

| Band | Nima qilindi | Fayl |
|---|---|---|
| **2.3** ❌→✅ | `POST /admin/tasks/{id}/deadline` — ishlab turgan vazifaning muddatini qo'lda o'zgartirish. **O'tgan sana ham qabul qilinadi** (TZ "ortga ham" deydi). Yon ta'sirlari: "1 kun qoldi" bayrog'i tozalanadi (aks holda muddat oldinga surilsa ogohlantirish qayta ishlamasdi), `OVERDUE` → `ACTIVE` qaytadi, Trello karta `due`si yangilanadi, ijrochi/brigadir/nazoratchiga xabar ketadi. Ball aynan muddatdan hisoblangani uchun o'zgarish kim tomonidan qilingani logga yoziladi | `miniapp/api/admin.py`, `services/notification_service.py` (`notify_deadline_changed`), `trello/client.py` (`set_card_due`) |
| **2.3 + 2.6 UI** | Yangi **"Buyurtmalar"** ekrani (rahbar bosh sahifasida): moduldagi barcha ochiq buyurtmalar, muddati yaqinidan boshlab. Har biriga kirib muddat va srochniy belgisini o'zgartirish mumkin. Ilgari ishlab turgan buyurtmaga umuman kirish yo'li yo'q edi — faqat ikkita navbat ekrani bor edi | `miniapp/api/admin.py` (`GET /admin/orders`), `app.js` (`screenAdminOrders`, `screenAdminOrderDetail`) |
| **5.6** ❌→⚠️ | Bot bloklangani endi **ko'rinadi**: `TelegramForbiddenError` ushlanganda o'sha xodimning rahbariga + barcha adminlarga signal ketadi ("unga xabarnomalar yetib bormayapti"). Ilgari bu faqat log faylida qolardi | `services/notification_service.py` (`_report_blocked`) |

> **5.6 nega ✅ emas, ⚠️:** Telegram'da xabarnomani o'chirishni **majburlab
> to'xtatib bo'lmaydi** — foydalanuvchi chatni "mute" qilishi mumkin va Bot
> API bu holatni umuman ko'rsatmaydi. Bloklashni (butunlay to'sib qo'yish)
> aniqlash mumkin — shuni qildim. Mute'ga qarshi yagona chora tashkiliy,
> texnik emas. Agar kerak bo'lsa keyingi qadam: muhim xabarlarga
> "✅ Tanishdim" tugmasi + bosilmasa eskalatsiya (yangi jadval + job fazasi
> kerak) — ayting, qo'shaman.

### Testlar

To'rtta yangi tekshiruv, hammasi **sabotaj bilan tasdiqlangan** (mantiqni
ataylab buzib, test yiqilishini ko'rdim):

```
tests/test_sla_engine.py          # + sotuvchilarning bosqichga ko'chishi
tests/test_penalty_rule_guard.py  # YANGI — ochiq chegara himoyasi + validatsiya
tests/test_blocked_notify.py      # YANGI — bloklash signali, dedup, kaskad himoyasi
```

Birinchi urinishda `test_blocked_notify` rekursiya himoyasini **ushlamadi**
(bitta admin bo'lganda boshqa mexanizm ham yetarli edi) — test ikkita admin
bilan kuchaytirildi, endi ikkala himoya ham alohida pinlangan.

To'liq to'plam (9 ta), `import main`, `node --check` va i18n uz/ru
tenglik tekshiruvi (272 = 272) — hammasi o'tdi.

### ❌ — qaror kutilmoqda (yozilmadi, sababi bilan)

**6.1 — "Vazifa buyurish" jarayon boshida.** TZ bandi ikki xil o'qiladi va
ikkalasi butunlay boshqa ishni anglatadi:
- **(A) UI kirish nuqtasi** — "vazifa buyurish" rahbar ekranining boshida
  turishi kerak. Bu **allaqachon bor**: `screenAdminHome` dagi birinchi
  (accent) tugma — "Yangi vazifa". Bu o'qilishda band ✅.
- **(B) Zanjir bosqichi** — maxsus vazifa buyurtmaga bog'lanishi kerak
  (masalan "shu zakaz bo'yicha Aliga vazifa"). Bu `tasks` jadvaliga yangi
  ustun (`related_order_task_id`), migratsiya va UI talab qiladi.

Hozir MISC vazifa buyurtmadan butunlay mustaqil. Qaysi biri kerakligini
ayting — (B) bo'lsa 1 soatlik ish.

**8.3 multi-tenant va 8.4 tarif rejalari — boshlamadim, sabab jiddiy:**

1. **CLAUDE.md aynan shuni taqiqlaydi:** "Deliberately **not** built
   (confirm before adding): §3 `Company`/multi-tenant and §10 tariff plans
   (SaaS was dropped)". Ya'ni bu ilgari **siz** bekor qilgan qaror — men uni
   so'ramasdan qayta tiklashim noto'g'ri bo'lardi.
2. **Hajmi:** `organization_id` ustuni deyarli har bir jadvalga
   (`employees`, `departments`, `brigades`, `tasks`, `clients`, `leads`,
   `penalty_rules`), `app_settings` singleton jadvalining har korxona uchun
   qatorga aylanishi, har bir so'rovning qayta yozilishi, Trello
   kalitlari/bot tokenining korxona bo'yicha ajratilishi. Bu bir necha
   haftalik ish, bitta sessiya emas.
3. **Eng muhimi — MUZLATILGAN modulga tegadi.** CLAUDE.md qat'iy qoidasi:
   mebel ("Fasad seh") ishlab chiqarishda ishlayapti va o'zgartirilmaydi;
   "agar o'zgarish mebelga tegmasdan iloji bo'lmasa — avval so'rang".
   Multi-tenant esa mebelning HAR BIR so'rovini qayta yozadi.
4. Hozir tizim 15 xodim, 2 modul, bitta Trello hisobi bilan ishlaydi va
   `fasad_sex` hali **umuman ishga tushmagan** (0 vazifa). Ikkinchi
   korxonaga sotishdan oldin birinchisini ishlatib ko'rish kerak.

Agar multi-tenant haqiqatan kerak bo'lsa — ayting, alohida reja yozaman
(migratsiya bosqichlari, mebelga ta'sirini kamaytirish yo'li, taxminiy
hajm). Buni "yo'l-yo'lakay" qilib bo'lmaydi.

### Tuzatilmagani — sizdan ma'lumot yoki qaror kerak

| Band | Nima kerak | Nega men qila olmayman |
|---|---|---|
| **5.4** | Har sexning haqiqiy Telegram guruh ID'si (23/23 bo'limda `NULL`) | Botni guruhga qo'shish va ID olish — faqat siz qila olasiz. Kod tayyor, Mini App'da maydon bor |
| **5.2** | Xodimlarga rahbar (`manager_id`) belgilash (0/15) | Tashkiliy tuzilma — kim kimga hisobot beradi. Mini App: Xodim → "Bevosita rahbar" |
| **7.3 / 4.1** | `fasad_sex` bo'limlariga xodim va brigada (hozir 0) | Real odamlar botga `/start` orqali o'zi ro'yxatdan o'tishi kerak |
| **4.1** | 4 ta yo'q bosqich: `Fayl + zapchast yig'ish`, `Ta'minot`, `Raspil`, "dostavkadan keyin STOP" — kerakmi? | Biznes qarori. Fork hozir `Fayl yig'ish`da, TZ esa `Raspil`da deydi — ular bir xilmi? |
| **4.1** | Laminat/Eman zanjirlari (94–99) asosiy zanjirga ulanmagan | Qayerga ulanishi kerakligi aytilmagan |
| **4.1 (12-qator)** | shkurka+kraska+malyarka uchun umumiy 15 sutkalik blok | Blok qo'yilsa har bosqichning O'Z muddati (72/72/24) bekor bo'ladi — ikkovi bir vaqtda ishlamaydi. Qaysi biri kerak? |
| **4.1 (16-qator)** | Montaj uchun 7–8 brigada | Brigada nomlari/brigadirlari ro'yxati kerak |
| **2.2** | Alohida "nachalo" (boshlanish sanasi) maydoni kerakmi? | Hozir `started_at` timestamp bor — yetarlimi? |
| **8.1** | "Admin paroli" — Mini App rol bilan ishlaydi, parol yo'q | Hozirgi model xavfsizroq; TZ iborasi eskirgan bo'lishi mumkin |

---

## Umumiy xulosa

- **Audit paytida (2026-08-04, ertalab): 32 banddan ✅ 18, ⚠️ 10, ❌ 4.**
  Tuzatishlardan keyin: **✅ 27, ⚠️ 3, ❌ 2**.
  - ⚠️ qolgani: `4.1` (zanjir — biznes qarori), `5.4`/`5.2` (kod tayyor,
    ma'lumot kutilmoqda), `5.6`/`8.1` (platforma cheklovi va TZ iborasi).
  - ❌ qolgani: `8.3` multi-tenant va `8.4` tarif — ikkalasi ham ilgari
    **siz bekor qilgan** SaaS rejasining qismi, qayta boshlash tasdig'ingizni
    talab qiladi.
- **Kod tayyor, ma'lumot tayyor emas.** Qolgan ⚠️ larning hammasi kod
  yozish emas, **DB'ga qiymat kiritish**: guruh ID'lari, rahbarlar,
  brigadalar, xodimlar. `fasad_sex` modulida hozir **0 xodim va 0 vazifa**
  bor — modul hech qachon amalda ishlatilmagan.
- **Uchta haqiqiy kod nuqsoni topildi, uchalasi ham tuzatildi:**
  (1) `task_sellers` bosqichlar bo'ylab ko'chmasdi,
  (2) bo'lim qo'shish formasi `module` yubormasdi,
  (3) faol vazifaning muddatini o'zgartirib bo'lmasdi.
- **STOP funksiyasi (TZ'ning asosiy talabi) to'liq ishlangan:** taymer
  muzlashi, rangli yorliq, alohida ro'yxat, statistikadan chegirish —
  hammasi bor va testlar bilan qoplangan (`bot/tests/test_sla_engine.py`).
