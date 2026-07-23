# Baza sxemasi (source of truth)

Ushbu hujjat `bot/db/models/` da aniqlangan SQLAlchemy modellariga mos ravishda yuritiladi.
`web/` shu sxemaga tayanib o'qish/yozish qiladi, lekin uni o'zgartirmaydi — barcha
migratsiyalar faqat Alembic (`bot/db/migrations/`) orqali amalga oshiriladi.

## Umumiy qoidalar

- Har bir jadvalda `id` (PK, autoincrement), `created_at`, `updated_at` ustunlari bor —
  bular `bot/db/base.py`dagi `TimestampedBase` orqali avtomatik qo'shiladi, alohida
  modellarda qayta yozilmaydi.
- `role` (employees) va `status` (tasks) ustunlari Python `Enum` orqali aniqlanadi
  (`bot/utils/enums.py`), lekin bazada **native Postgres ENUM emas**, oddiy
  `VARCHAR + CHECK constraint` sifatida saqlanadi (`native_enum=False`). Sabab: yangi
  rol/status qo'shilganda Postgres native enum'ni `ALTER TYPE` qilish murakkab va
  bloklovchi bo'lishi mumkin; VARCHAR bilan bu oddiy migratsiya.

## Jadvallar

### departments — Yo'nalishlar/Sexlar
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| name | VARCHAR(100) | masalan: "Fasad sexi", "Stolyar", "Shkurka", "Kraska" |
| trello_list_id | VARCHAR(50) | shu yo'nalishga tegishli vazifalar yoziladigan Trello ro'yxati (list) ID'si; NULL = hali sozlanmagan, `task_service.create_task()` bunday yo'nalish uchun aniq xato ko'taradi (`4aeafdfa9317` migratsiyasi) |
| next_department_id | FK -> departments.id | NULL bo'lishi mumkin; standart ishlab chiqarish ketma-ketligidagi KEYINGI bo'lim (masalan Stolyar.next = Shkurka.id, 6.1/7.4-band, `576f19bf5629` migratsiyasi). NULL = zanjirning so'nggi bosqichi. `task_service.advance_task_stage()` shu ustunga qarab buyurtmani avtomatik keyingi bosqichga o'tkazadi. `/deptchain` buyrug'i orqali (`handlers/admin/settings.py`) sozlanadi |
| auto_reassign_after_48h | BOOLEAN | default: false (8.3-band, `470b837c8dae` migratsiyasi). `True` bo'lsa, shu bo'limdagi OVERDUE buyurtma muddatidan 48 soatdan ortiq kechiksa `overdue_watch_job` AVTOMATIK signal beradi (brigada tanlovi va yakuniy tasdiq qo'lda, `handlers/admin/reassign_task.py`). `/autoreassign` buyrug'i orqali sozlanadi |
| starts_stopped | BOOLEAN | default: false (Fasad sex TZ: buyurtma STOPPED holatda ochilishi, `2ec88464a4f8` migratsiyasi). `True` bo'lsa, `task_service.create_task()` yangi vazifani `ACTIVE` o'rniga `STOPPED` holatda yaratadi va bir vaqtda `StopLog` qatorini ham yozadi ("joy tayyor bo'lishini kutmoqda") — shu qator bo'lmasa `timer_service.resume_task()` ishlamas edi. Mini App'ning `POST /admin/departments` / `POST /admin/departments/{id}` orqali sozlanadi |
| module | VARCHAR(20) | default: `'mebel'` (Fasad sex TZ, Phase 0 — Mini App modul almashtirgichi, `d33c76d946db` migratsiyasi). Shu bo'lim qaysi ishlab chiqarish moduliga tegishli — `"mebel"` (asosiy, standart) yoki `"fasad_sex"` (yangi, parallel zanjir); enum/CHECK emas, oddiy VARCHAR (repo konvensiyasi — 3-modul kelajakda qo'shilsa, cheklovsiz kengayadi). `miniapp/api/common.py`'ning `GET /me`'si `available_modules`'ni shu ustunga qarab hisoblaydi (rol + `employee.department_id` bo'yicha) — frontend shu ro'yxatga qarab modul tanlash ekranini ko'rsatadi/o'tkazib yuboradi |
| factory_name | VARCHAR(100), NULL | Fasad sex TZ §9 "ikkinchi zavod" (`3137620903a2` migratsiyasi). `module`dan MUSTAQIL — `module` qaysi ishlab chiqarish TIZIMIga (mebel/fasad_sex), `factory_name` esa qaysi jismoniy ZAVOD/FILIALga tegishli ekanini belgilaydi (2+ jismoniy joylashuv statistikasi aralashmasligi uchun, hech biri ikkinchisidan hisoblanmaydi). NULL = hali belgilanmagan. `stats_service.get_monthly_stats(factory_name=...)` ixtiyoriy filtr parametri sifatida ishlatadi (`Employee.department_id -> Department.factory_name` join, `None` — filtrsiz, avvalgidek). Mini App'ning `POST /admin/departments` / `POST /admin/departments/{id}` orqali sozlanadi (`GET /admin/stats?factory_name=` orqali o'qiladi) — hozircha alohida UI/zavod-tanlash ekrani yo'q |
| created_at / updated_at | TIMESTAMPTZ | |

**Bog'lanishlar**: `brigades` (1-M), `employees` (1-M), `tasks` (1-M, `current_department_id` orqali), `next_department` (M-1, o'z-o'ziga, ixtiyoriy).

### brigades — Brigadalar
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| name | VARCHAR(100) | |
| department_id | FK -> departments.id | NOT NULL |
| brigadier_id | FK -> employees.id | NULL bo'lishi mumkin (brigadir hali tayinlanmagan bo'lishi mumkin) |
| created_at / updated_at | TIMESTAMPTZ | |

**Bog'lanishlar**: `department` (M-1), `brigadier` (M-1 -> employees, ixtiyoriy).

### employees — Xodimlar
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| telegram_id | BIGINT, UNIQUE | NULL bo'lishi mumkin — botga hali ulanmagan xodim uchun |
| full_name | VARCHAR(150) | |
| phone_number | VARCHAR(20), UNIQUE | NULL bo'lishi mumkin; `2d518eef70c7` migratsiyasi (5.1-band, dublikat oldini olish) |
| trello_username | VARCHAR(100) | NULL; xodim yaratish/tahrirlashda kiritilsa, `trello.get_member_id()` orqali darhol tekshiriladi (`handlers/admin/employee_management.py`) |
| trello_member_id | VARCHAR(50) | NULL; Trello a'zo ID'si (24 xonali hex, `470b837c8dae` migratsiyasi, 6.2-band). `trello_username` kiritilganda avtomatik to'ldiriladi — `task_service.create_task()`/`advance_task_stage()`/`activate_pending_stage()` shu orqali kartaga real a'zo qo'shadi/olib tashlaydi |
| gmail | VARCHAR(150) | NULL |
| role | VARCHAR (Enum) | `admin`, `supervisor`, `brigadier`, `worker`, `seller`, `observer` |
| department_id | FK -> departments.id | NULL bo'lishi mumkin (masalan, admin/observer uchun) |
| brigade_id | FK -> brigades.id | xodim A'ZOSI bo'lgan brigada (`c54dee342844` migratsiyasi); NULL — hali biriktirilmagan |
| next_payment_date | DATE | default: joriy oyning 15-sanasi (8.5-band); tizim minus ball to'planganda buni siljitib boradi |
| is_active | BOOLEAN | default: true; ishdan bo'shatilganda false qilinadi ("O'CHIRISH" tugmasi soft-delete) |
| language | VARCHAR(2) | default: 'uz' (`a1c9f3e7d502` migratsiyasi); Mini App profil ekranidagi til tanlovi ("uz"/"ru") — `bot/miniapp/api/common.py`ning `POST /me/language`si yozadi |
| created_at / updated_at | TIMESTAMPTZ | |

**Bog'lanishlar**: `department` (M-1), `brigade` (M-1, a'zolik), `led_brigades`
(1-M -> brigades.brigadier_id, rahbarlik), `task_assignments` (1-M), `kpi_logs`
(1-M), `stop_logs` (1-M).

> `brigades` va `employees` orasida ENDI ikkita mustaqil FK bor: `brigades.brigadier_id`
> (kim rahbar) va `employees.brigade_id` (kim a'zo). Ikkalasi ham nullable, shuning
> uchun jadval yaratish tartibida haqiqiy tsikl yo'q, lekin Alembic autogenerate buni
> "unresolvable cycle" deb ogohlantiradi — bu faqat autogenerate'ning jadval
> tartiblash evristikasiga oid, amaldagi migratsiyalarga ta'sir qilmaydi.

### tasks — Vazifalar, Zakazlar, MISC topshiriqlar (9-band) va ko'p bosqichli progressiya (6.1/7.4-band)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| trello_card_id | VARCHAR(50), index (UNIQUE EMAS) | Trello karta ID'si; **MISC** (`task_type`) uchun har doim NULL. Ko'p bosqichli buyurtmada (6.1/7.4-band) bir nechta bosqich-qatori BIR XIL kartani bo'lishishi mumkin — shu sabab UNIQUE emas, oddiy index (`576f19bf5629` migratsiyasi, avvalgi `tasks_trello_card_id_key` UNIQUE cheklovi olib tashlandi). Bir vaqtda faqat BITTA `COMPLETED` bo'lmagan qator "joriy" hisoblanadi — bu ilova darajasidagi invariant, `task_repo.get_by_trello_card_id()` shunga mos qaytaradi |
| task_type | VARCHAR (Enum) | `order` (Trello bilan bog'liq buyurtma) / `misc` (Trello'siz alohida topshiriq, 9-band). Default: `order` |
| title | VARCHAR(255) | MISC uchun topshiriq matnining o'zi (qisqartirilgan, 255 belgigacha) |
| description | TEXT | NULL; MISC uchun to'liq topshiriq matni |
| deadline | TIMESTAMPTZ, NULL bo'lishi mumkin | joriy bosqich muddati. `PENDING_SETUP` holatida NULL — nazoratchi/admin hali kiritmagan (`576f19bf5629` migratsiyasi, 6.1/7.4-band) |
| status | VARCHAR (Enum) | `active`, `completed`, `overdue`, `stopped`, **`pending_setup`** (yangi, 6.1/7.4-band: bosqich yangi bo'limga keldi, muddat/xodim hali belgilanmagan) — ORDER va MISC uchun BIR XIL (`timer_service.py` ikkalasini ham farqlamaydi; MISC hech qachon `pending_setup`ga o'tmaydi — 9-band vazifalar bosqich zanjiriga kirmaydi) |
| current_department_id | FK -> departments.id | NULL bo'lishi mumkin (`3d115fff2f54`); MISC yaratishda aniq so'ralmaydi — birinchi biriktirilgan xodimning bo'limidan avtomatik olinadi |
| started_at | TIMESTAMPTZ | Ko'p bosqichli oqimda: yangi bosqich yaratilgan daqiqa (bo'limga "yetib kelgan" payt, 8.1-band talabiga mos — muddat hali kiritilmagan bo'lsa ham taymer boshlanish nuqtasi shu) |
| finished_at | TIMESTAMPTZ | NULL |
| previous_task_id | FK -> tasks.id | NULL bo'lishi mumkin; bir xil buyurtmaning OLDINGI bosqich-qatoriga ishora (zanjir, `576f19bf5629` migratsiyasi). Ildiz bosqich (buyurtmaning birinchi qatori) uchun NULL — "nechta ZAKAZ (buyurtma, bosqich emas) topshirdi" ko'rsatkichi kerak bo'lsa, `previous_task_id IS NULL` orqali sanaladi |
| day_left_notified_at | TIMESTAMPTZ, NULL | 7.2-band (`470b837c8dae`): "muddatga 1 kun qoldi" signali yuborilgan payt — `overdue_watch_job` qayta yubormasligi uchun (bir marta yozilgach, shu bosqich uchun qayta signal kelmaydi) |
| reassignment_signaled_at | TIMESTAMPTZ, NULL | 8.3-band (`470b837c8dae`): bo'lim `auto_reassign_after_48h=true` bo'lganda, 48 soatdan ortiq kechikkanda `overdue_watch_job` avtomatik signal yozgan payt (rahbar hali brigada tanlamagan/tasdiqlamagan bo'lishi mumkin — bu faqat signal, `reassigned_at`dan farqli) |
| reassigned_at | TIMESTAMPTZ, NULL | 8.3-band (`470b837c8dae`): rahbar brigadani QO'LDA almashtirgan payt (`task_service.reassign_task_brigade()`). Bo'lsa, `penalty_service.calculate_and_apply_task_penalty()` kechikishni `deadline` o'rniga shu vaqtdan hisoblaydi — eski brigada allaqachon darhol jarimalangan davrni yangi brigadaga qayta hisoblamaslik uchun |
| trello_checklist_id | VARCHAR(50), NULL | 6.2-band (`470b837c8dae`): kartadagi "Bosqichlar" checklist ID'si — bir xil `trello_card_id`ni bo'lishuvchi barcha bosqich-qatorlariga bir xil qiymat ko'chiriladi (`advance_task_stage()`) |
| client_id | FK -> clients.id, NULL | 12-band (`b3f7a1c9d204`, 4-bosqich): bosqich o'tganda/"Stop" bosilganda avtomatik xabarnoma yuboriladigan mijoz. MISC vazifada har doim NULL (`create_misc_task()` client_id qabul qilmaydi). `advance_task_stage()` bosqichdan-bosqichga `trello_checklist_id` kabi ko'chiradi |
| created_at / updated_at | TIMESTAMPTZ | |

**MISC vazifalar KPI/jarima tizimiga ORDER bilan BIR XIL qoidada ta'sir qiladi**
(`penalty_service.calculate_and_apply_task_penalty` `task_type`ni umuman
tekshirmaydi — faqat `deadline`/`finished_at`/`current_department_id`ga
qaraydi) — 9-band talabi: "minus ball xuddi shu qoidada yoziladi". Faqat
`jobs/daily_sync_job.py` MISC vazifalarni chetlab o'tadi (Trello karta yo'qligi
sabab).

**Ko'p bosqichli progressiya (6.1/7.4-band)**: `departments.next_department_id`
zanjiriga ko'ra, bir buyurtma bir nechta bo'limdan KETMA-KET o'tadi — har
bosqich **alohida `tasks` qatori** sifatida saqlanadi (bitta Task+child-jadval
emas — sabab: `penalty_service`/`stats_service`/`timer_service` allaqachon
bitta `Task` qatori ustida ishlaydi, bu qarordan bu modullarga tegilmadi).
Oqim: ishchi "Yakunlash" bosganda `task_service.advance_task_stage()`
chaqiriladi -> joriy bo'lim `next_department_id`ga qarab: (a) `NULL` bo'lsa —
buyurtma to'liq tugagan, hech narsa yaratilmaydi; (b) bo'lsa — Trello karta
DARHOL keyingi bo'lim list'iga ko'chiriladi (`trello.move_card_to_list()`) va
yangi `pending_setup` qator yaratiladi (`previous_task_id` bilan zanjirlangan,
bir xil `trello_card_id`, `deadline=NULL`). Keyingi bo'lim nazoratchisi/admini
(`notify_stage_pending_setup`) signal oladi va `handlers/admin/advance_task.py`
orqali muddat+xodim(lar)ni qo'lda kiritadi (`task_service.activate_pending_stage()`
— 8.1-band bo'yicha bosqich muddatini tizim o'zi taxmin qilmaydi). **MUHIM**:
`timer_service.finish_task()` bu mantiqni umuman chaqirmaydi (sof qoladi) —
`advance_task_stage()` faqat ishchining "Yakunlash" handler'idan chaqiriladi.
`daily_sync_job`ning Trello karta arxivlanganda avtomatik yopish yo'li ham buni
chaqirmaydi (karta arxivlanishi = butun buyurtmaning TERMINAL yopilishi, keyingi
bosqichga o'tish emas — ikkovi ziddiyatli bo'lardi). `daily_sync_job._list_open_tasks()`
`pending_setup` qatorlarni chetlab o'tadi (`deadline=NULL` bilan `determine_status()`
chaqirilsa yiqiladi, va muddat hali yo'qligi sabab label tekshiruvi ma'nosiz).

**6.2-band (karta a'zo + checklist)**: `create_task()` kartaga har bir
biriktirilgan xodimni (agar `trello_member_id` bo'lsa) a'zo qilib qo'shadi va
bo'lim zanjiri bo'yicha "Bosqichlar" checklist yaratadi (`trello_checklist_id`).
`advance_task_stage()` eski bosqich checklist punktini "complete" belgilaydi va
eski xodimlarni kartadan a'zolikdan chiqaradi; `activate_pending_stage()` yangi
bosqich xodimlarini qayta a'zo qilib qo'shadi. Hammasi ikkinchi-darajali effekt
— xato bo'lsa faqat log qilinadi, asosiy oqim (karta/baza yozuvi) to'xtamaydi.

**7.2-band (muddat kuzatuvi)** va **8.3-band (avto brigadaga o'tkazish)**:
`jobs/overdue_watch_job.py` har soat: (1) `deadline` 24 soat ichida bo'lgan
ACTIVE/STOPPED tasklarga "1 kun qoldi" signali (`day_left_notified_at`), (2)
`deadline` o'tib ketgan tasklarni `OVERDUE`ga o'tkazadi, (3) bo'limi
`auto_reassign_after_48h=true` bo'lgan 48 soatdan ortiq OVERDUE tasklarga
brigadaga-o'tkazish signali (`reassignment_signaled_at`) beradi. Yakuniy
brigada tanlovi va tasdiq qo'lda (`task_service.reassign_task_brigade()`,
`handlers/admin/reassign_task.py`): eski brigadaga DARHOL jarima, task
`COMPLETED` qilinmaydi, `reassigned_at` belgilanadi — yakunlanganda
`penalty_service` kechikishni shu vaqtdan hisoblaydi (`deadline`dan emas).

**Bog'lanishlar**: `current_department` (M-1), `assignments` (1-M, cascade delete),
`stop_logs` (1-M, cascade delete), `previous_task` (M-1, o'z-o'ziga, ixtiyoriy).

### task_assignments — Vazifa <-> Xodim (M-to-M)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| task_id | FK -> tasks.id | |
| employee_id | FK -> employees.id | |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE(task_id, employee_id)` — bitta xodim bitta vazifaga faqat bir marta biriktiriladi.

**Bog'lanishlar**: `task` (M-1), `employee` (M-1).

### kpi_logs — Ball/Jarima tarixi
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| employee_id | FK -> employees.id | |
| score | INTEGER | masalan: -1, -3, +1 |
| reason | TEXT | |
| created_at / updated_at | TIMESTAMPTZ | |

**Bog'lanishlar**: `employee` (M-1).

### stop_logs — "Stop" tugmasi hodisalari
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| task_id | FK -> tasks.id | |
| employee_id | FK -> employees.id | kim "Stop" bosgani |
| reason | TEXT | sabab (majburiy, 7.5-band) |
| stopped_at | TIMESTAMPTZ | |
| resumed_at | TIMESTAMPTZ | NULL — hali davom ettirilmagan bo'lsa |
| created_at / updated_at | TIMESTAMPTZ | |

**Bog'lanishlar**: `task` (M-1), `employee` (M-1).

### penalty_rules — Kechikish jarima jadvali (8.2-band)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| department_id | FK -> departments.id | NULL = barcha yo'nalishlar uchun global qoida |
| min_hours_late | INTEGER | oraliq boshi (inklyuziv) |
| max_hours_late | INTEGER | oraliq oxiri (eksklyuziv); NULL = ochiq yuqori chegara |
| score | INTEGER | shu oraliqdagi kechikish uchun JAMI (kumulyativ) ball, masalan -8 |
| created_at / updated_at | TIMESTAMPTZ | |

Foydalanuvchi tasdiqlagan boshlang'ich qiymatlar (global, `835647e37c2a` migratsiyasida
seed qilingan, `f98817708ac9` migratsiyasida +24 soatga siljitilgan — pastga qarang):

| min_hours_late | max_hours_late | score |
|---|---|---|
| 24 | 48 | -1 |
| 48 | 72 | -2 |
| 72 | 96 | -5 |
| 96 | 120 | -8 |

120 soatdan keyingi bosqich hali kelishilmagan — shunday holatda `find_applicable_rule`
atayin `None` qaytaradi (oxirgi qiymatga "yopishib qolmaydi"), `penalty_service`
esa `PenaltyRuleNotConfiguredError` ko'taradi. Yangi bosqich qo'shish uchun kodga
tegish shart emas, faqat yangi qator yetarli.

**24 soatlik "grace period" (3-bosqich, `f98817708ac9`)**: 0-24 soat kechikish
uchun bracket ATAYIN yo'q — `penalty_service.calculate_and_apply_task_penalty()`
`hours_late < 24` bo'lsa hech qanday qoida qidirmasdan bo'sh ro'yxat qaytaradi
(kod darajasida, DB qatoriga ehtiyoj yo'q). `dayIndex = hours_late // 24`
formulasidan tabiiy kelib chiqadi: dayIndex=0 -> jarima yo'q.

**Bog'lanishlar**: `department` (M-1, ixtiyoriy).

### app_settings — Tizim sozlamalari (16-band, SINGLETON jadval)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | doim faqat bitta qator (id=1) |
| reminder_schedule | JSON | 7.3-band (`470b837c8dae` migratsiyasi, eski `remind_time` TIME ustuni o'rniga): `[{"time": "HH:MM", "urgency": "info"\|"warning"\|"urgent"}, ...]` — kun davomida bir necha marta, eskalatsiya darajasi bilan kuchayib boradigan eslatma jadvali. Default: 09:00/13:00 (info), 15:00 (warning), 17:00 (urgent) |
| default_penalty_multiplier | FLOAT | `penalty_rules.score`ga qo'llanadigan global ko'paytiruvchi (default: 1.0) |
| brigade_share_ratio | FLOAT | ishchi minus balidan brigadirga o'tadigan ulush (8.4-band, default: 0.33 — yakuniy tasdiqlangan qiymat) |
| balls_per_day_shift | INTEGER | har N minus ball uchun to'lov kuni 1 kunga suriladi (8.5-band, default: 5) |
| plus_ball_per_day | INTEGER | 8.4-band (`f98817708ac9`): muddatdan oldin tugatilgan har TO'LIQ kun uchun plus ball (default: 1) |
| plus_ball_max_days | INTEGER | plus ball necha kungacha hisoblanadi, undan ortig'iga qo'shilmaydi — cap (default: 2) |
| financial_flag_threshold_days | INTEGER | 8.6-band 1-qoida: bosqich shuncha kundan ORTIQ davom etsa moliyaviy taklif bayroqlanadi (default: 5) |
| advance_threshold_percent | INTEGER | 8.6-band 2-qoida: avans shu %dan ko'p/teng olingan bo'lsa qoida ishga tushadi (default: 80) |
| advance_waiver_percent | INTEGER | shu holatda mijozdan qolgan necha % talab qilinmaydi (default: 20) |
| report_time | VARCHAR(5) | 10.2-band (`b3f7a1c9d204`, 4-bosqich): kunlik/haftalik/oylik Telegram hisobotlari shu vaqtda (HH:MM, Toshkent) yuboriladi (default: `20:00`). Haftalik — yakshanba, oylik — har oyning 1-sanasi (kun tanlovi sozlanuvchan emas, TZda so'ralmagan) |
| lead_follow_up_threshold_days | INTEGER | 13.3-band (`ff165aafd9b1`, 5-bosqich): necha kun lidga aloqa bo'lmasa mas'ul sotuvchiga eslatma boradi (default: 7, foydalanuvchi bilan tasdiqlangan) |
| sales_board_lists | JSON | 6.1-band (`ff165aafd9b1`, 5-bosqich): `{"ezza": {"new_lead": list_id, "contacted": ..., "offer_sent": ..., "agreed": ..., "closed": ...}, "melores": {...}}` — har (brand, bosqich) juftligi uchun Trello list ID. `departments.trello_list_id` bilan bir xil naqsh: bot UI orqali EMAS, to'g'ridan-to'g'ri bazada sozlanadi. Default: hamma qiymat `NULL` (haqiqiy Ezza/Melores boardlari hali yaratilmagan) |
| created_at / updated_at | TIMESTAMPTZ | |

`f490887dee10` migratsiyasi orqali yaratilgan va bitta seed qator bilan
boshlang'ich qiymatlarga ega (5 ta yangi ustun `f98817708ac9`da, `report_time`
`b3f7a1c9d204`da qo'shilgan). Har doim `services/settings_service.py` orqali
(xotirada keshlangan holda) o'qiladi/yangilanadi — jadvalga to'g'ridan-to'g'ri
murojaat qilinmaydi. `reminder_schedule` o'zgarganda `jobs/reminder_job.
schedule_all()`, `report_time` o'zgarganda `jobs/report_job.schedule_all()`
barcha mos APScheduler job'larini (`main.py`da ro'yxatdan o'tkazilgan) olib
tashlab, qayta yaratadi (`handlers/admin/settings.py`ning `/reminders` va
`/settings` oqimlari har o'zgarishdan keyin shu funksiyalarni chaqiradi).
Faqat `Role.ADMIN`/`Role.SUPERVISOR` o'zgartira oladi (`middlewares/auth.py:
RoleAccessMiddleware`). 10 ta skalyar qiymat (yuqoridagi jadval, `lead_follow_up_
threshold_days` shu jumladan) `/settings` orqali xuddi shu yo'l bilan
tahrirlanadi. `sales_board_lists` bundan mustasno — `departments.trello_list_id`
kabi bot UI orqali EMAS, to'g'ridan-to'g'ri bazada sozlanadi (haqiqiy Ezza/
Melores Trello boardlari yaratilgach).

`BASE_PAYMENT_DAY` (8.5-banddagi bazaviy to'lov kuni, 15) bu ro'yxatda YO'Q —
`penalty_service.py`da hali konstanta bo'lib qolmoqda, chunki so'ralgan 4 ta
sozlama ro'yxatiga kirmagan edi.

### financial_suggestions — Moliyaviy javobgarlik TAKLIFLARI (8.6-band, 3-bosqich)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| task_id | FK -> tasks.id | qaysi bosqich-qatoriga tegishli |
| kind | VARCHAR | `wage_deduction` (1-qoida) yoki `advance_waiver` (2-qoida) |
| status | VARCHAR | doim `pending_manager_review` bilan yaratiladi — tizim hech qachon o'zi `approved`/`rejected` qilmaydi, bu BOSHQA (hali qurilmagan) modul ishi |
| applicable | BOOLEAN | qoida shu holatga tatbiq etiladimi |
| stage_duration_days | INTEGER, NULL | `wage_deduction`: bosqich necha kun davom etgani |
| amount_withheld_by_customer | FLOAT, NULL | `wage_deduction`: mijoz ushlab qolgan summa — HAR DOIM qo'lda kiritiladi (tizimda moliya moduli yo'q), avtomatik bayroqlashda `NULL` ("kutilmoqda") |
| suggested_deduction_amount | FLOAT, NULL | `wage_deduction`: taklif qilingan ushlab qolish summasi = `amount_withheld_by_customer * 0.5` (dumaloqlashtirilmagan) |
| advance_percent_paid | INTEGER, NULL | `advance_waiver`: qo'lda kiritilgan avans foizi |
| order_total_value | FLOAT, NULL | `advance_waiver`: qo'lda kiritilgan buyurtma summasi |
| waived_amount | FLOAT, NULL | `advance_waiver`: kechiriladigan summa = `order_total_value * (advance_waiver_percent/100)` |
| created_at / updated_at | TIMESTAMPTZ | |

`f98817708ac9` migratsiyasida yaratilgan. Sof hisoblash `services/financial_service.py`
(`calculate_wage_deduction_suggestion`, `calculate_advance_waiver`) — hech qanday
tashqi API chaqirmaydi, faqat son qaytaradi. `wage_deduction` yozuvlari
`jobs/overdue_watch_job.py`ning `_process_financial_flags()` bosqichi orqali
har soat AVTOMATIK yaratiladi (`financial_service.flag_long_duration_stage()`,
bitta task+kind uchun bir marta — `FinancialSuggestionRepository.exists_for_task`
orqali idempotent), summa esa hali NULL ("kutilmoqda" holati) — kelajakdagi
admin UI (hali qurilmagan, 4-bosqich statistikasi bilan bog'liq) buni
to'ldiradi. `advance_waiver` uchun avtomatik ma'lumot manbai umuman yo'q
(avans/buyurtma summasi tizimda saqlanmaydi) — `financial_service.
create_advance_waiver_suggestion()` tayyor, lekin hozircha hech qayerdan
chaqirilmaydi, faqat kelajakdagi qo'lda-kiritish UI uchun interfeys.

**Bog'lanishlar**: `task` (M-1).

### clients — Mijozlar (12-band, 4-bosqich)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| full_name | VARCHAR(150) | |
| phone_number | VARCHAR(20), UNIQUE, NULL | admin vazifa yaratishda kiritadi (`services/client_service.find_or_create_client`, `handlers/admin/task_create.py`) — dublikat oldini olish |
| telegram_id | BIGINT, UNIQUE, NULL | mijozning o'zi `/mijoz` orqali telefon raqamini kiritib bog'laydi (`client_service.link_client_to_telegram`, `registration_service.link_employee_to_telegram` bilan bir xil naqsh — yangi yozuv bu yerda yaratilmaydi, faqat admin oldindan kiritganiga bog'lanadi). `NULL` bo'lsa xabarnoma jim o'tkazib yuboriladi |
| created_at / updated_at | TIMESTAMPTZ | |

`b3f7a1c9d204` migratsiyasida yaratilgan. Ataylab minimal va CRM-spetsifik
bo'lmagan maydonlar bilan cheklangan — 5-bosqich (Sotuv CRM) shu jadvalni
qayta ishlatishi/kengaytirishi mumkin (pastdagi "Hali aniqlanmagan" bo'limiga
qarang). `tasks.client_id` orqali bog'lanadi; `notification_service.
notify_client_stage_advanced()`/`notify_client_task_stopped()` faqat
`telegram_id IS NOT NULL` bo'lganda xabar yuboradi (SMS kanal — TZ 19-band
#11 — foydalanuvchi "faqat Telegram" deb tasdiqlagan, 2026-07-17, shu sabab
qurilmagan).

**Bog'lanishlar**: `tasks` (1-M, `client_id` orqali).

### leads — Sotuv varonkasi lidlari (13.1-band, 5-bosqich)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| client_id | FK -> clients.id | `client_service.find_or_create_client` orqali telefon bo'yicha topiladi/yaratiladi |
| brand | VARCHAR | `ezza` \| `melores` (`LeadBrand` enum, `native_enum=False`) |
| stage | VARCHAR | `new_lead` -> `contacted` -> `offer_sent` -> `agreed` -> `closed_won`/`closed_lost` (`LeadStage` enum). Ilgari yo'nalishda faqat shu tartibda o'tadi (`sales_service.advance_lead_stage`); yopish (won/lost) istalgan ochiq bosqichdan mumkin (`sales_service.close_lead`) |
| assigned_seller_id | FK -> employees.id | mas'ul sotuvchi (`Role.SELLER`) |
| trello_card_id | VARCHAR(50), NULL | Ezza/Melores board'idagi karta |
| last_contacted_at | TIMESTAMPTZ | eng oxirgi qo'ng'iroq vaqti (yoki lid yaratilgan vaqt, hali qo'ng'iroq bo'lmasa) — `jobs/lead_follow_up_job.py` shu ustunga qarab "uzoq aloqasiz" lidlarni topadi, `sales_service.add_call_log()` yozganda yangilanadi |
| created_at / updated_at | TIMESTAMPTZ | |

`11e2c2cee985` migratsiyasida yaratilgan. Ishlab chiqarish `tasks`/`task_
assignments`/`penalty_service` mantig'idan TO'LIQ mustaqil (5-bosqich
hujjatidagi arxitektura qarori) — muddat/KPI jarima tizimiga umuman kirmaydi.
TZ 6.1-band: Ezza/Melores boardlarida faqat 5 ta list bor (Yangi lid/Aloqa/
Taklif/Kelishildi/Yopildi) — `closed_won` va `closed_lost` ikkalasi ham bitta
"Yopildi" list'iga tushadi, farq faqat `stage` ustunida saqlanadi. Trello list
ID'lari `app_settings.sales_board_lists`dan olinadi (`sales_service.
_resolve_list_id`) — sozlanmagan bo'lsa `SalesBoardNotConfiguredError`.

**Bog'lanishlar**: `client` (M-1), `assigned_seller` (M-1, `employees`), `call_logs` (1-M).

### call_logs — Qo'ng'iroqlar bazasi (13.2-band, 5-bosqich)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| lead_id | FK -> leads.id | |
| recorded_by_id | FK -> employees.id | yozuvni kim kiritgani (odatda mas'ul sotuvchi) |
| content | TEXT, NULL | matn shaklidagi qo'ng'iroq eslatmasi |
| audio_file_id | VARCHAR(200), NULL | Telegram ovozli xabar (`voice`) file_id'si |
| called_at | TIMESTAMPTZ | yozuv kiritilgan payt (`sales_service.add_call_log`, `datetime.now()`) |
| created_at / updated_at | TIMESTAMPTZ | |

`11e2c2cee985` migratsiyasida yaratilgan. **Faqat qo'lda kiritish** (Telegram
matn yoki ovozli xabar, `handlers/sales/leads.py`) — IP-telefoniya
integratsiyasi (TZ 19-band #7) ataylab QURILMAGAN: foydalanuvgi bilan
2026-07-17 tasdiqlangan, chunki hech qanday provayder tanlanmagan va
provayder-siz webhook qabul qiluvchi kod sinovdan o'tkazib bo'lmaydigan
"o'lik kod" bo'lar edi. Provayder tanlanganda bu ALOHIDA, kattaroq loyihalash
talab qiladigan ish (`content`/`audio_file_id`dan tashqari webhook-spetsifik
ustunlar kerak bo'ladi). `content`/`audio_file_id`dan KAMIDA bittasi bo'lishi
shart (`sales_service.add_call_log` tekshiradi, DB darajasida emas).

**Bog'lanishlar**: `lead` (M-1), `recorded_by` (M-1, `employees`).

## Munosabatlar sxemasi (qisqacha)

```
departments 1───M brigades M───1 employees (brigadier_id, ixtiyoriy)
departments 1───M employees
departments 1───M tasks (current_department_id)
departments 1───1 departments (next_department_id, ixtiyoriy — bosqich zanjiri)

tasks 1───M task_assignments M───1 employees
tasks 1───M stop_logs M───1 employees
tasks 1───M financial_suggestions
tasks 1───1 tasks (previous_task_id, ixtiyoriy — bosqich zanjiri)
tasks M───1 clients (client_id, ixtiyoriy)

employees 1───M kpi_logs

clients 1───M leads
leads 1───M call_logs M───1 employees (recorded_by_id)
leads M───1 employees (assigned_seller_id)
```

## Hali aniqlanmagan / keyingi bosqichda qo'shiladigan jadvallar

- `clients` 4-bosqichda (`b3f7a1c9d204`), `leads`/`call_logs` 5-bosqichda
  (`11e2c2cee985`) YARATILDI — yuqoridagi jadvallarga qarang.
- IP-telefoniya integratsiyasi (call_logs'ning avtomatik manbai, TZ 19-band
  #7) ATAYLAB QURILMAGAN — provayder tanlanmagan (2026-07-17 tasdiqlangan).
  Provayder tanlanganda alohida loyihalash kerak bo'ladi.
- `organizations` — 15-band, multi-tenant (SaaS) fazasi uchun.

> `extra_tasks` alohida jadval sifatida REJALASHTIRILMAGAN — 9-band "Vazifalar"
> moduli allaqachon `tasks.task_type=misc` orqali amalga oshirilgan (alohida
> jadvalsiz, mavjud `tasks` jadvaliga qo'shimcha ustun bilan).

## Hal qilingan bo'shliq: `employees.brigade_id` (`c54dee342844` migratsiyasi)

Ilgari `employees`da faqat `department_id` bor edi, xodim qaysi **brigada**ga
a'zoligini bildiruvchi ustun yo'q edi (faqat `brigades.brigadier_id` orqali kim
brigadir ekani bilinardi). Endi `employees.brigade_id` qo'shildi — shu orqali
`notification_service.py` xodimning brigadirini (`employee.brigade.brigadier`)
avtomatik topib, unga ham xabar yubora oladi.
