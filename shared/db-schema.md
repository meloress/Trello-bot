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
| trello_username | VARCHAR(100) | NULL |
| gmail | VARCHAR(150) | NULL |
| role | VARCHAR (Enum) | `admin`, `supervisor`, `brigadier`, `worker`, `seller`, `observer` |
| department_id | FK -> departments.id | NULL bo'lishi mumkin (masalan, admin/observer uchun) |
| brigade_id | FK -> brigades.id | xodim A'ZOSI bo'lgan brigada (`c54dee342844` migratsiyasi); NULL — hali biriktirilmagan |
| next_payment_date | DATE | default: joriy oyning 15-sanasi (8.5-band); tizim minus ball to'planganda buni siljitib boradi |
| is_active | BOOLEAN | default: true; ishdan bo'shatilganda false qilinadi ("O'CHIRISH" tugmasi soft-delete) |
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

Foydalanuvchi tasdiqlagan boshlang'ich qiymatlar (global, `835647e37c2a` migratsiyasida seed qilingan):

| min_hours_late | max_hours_late | score |
|---|---|---|
| 0 | 24 | -1 |
| 24 | 48 | -2 |
| 48 | 72 | -5 |
| 72 | 96 | -8 |

96 soatdan keyingi bosqich hali kelishilmagan — shunday holatda `find_applicable_rule`
atayin `None` qaytaradi (oxirgi qiymatga "yopishib qolmaydi"), `penalty_service`
esa `PenaltyRuleNotConfiguredError` ko'taradi. Yangi bosqich qo'shish uchun kodga
tegish shart emas, faqat yangi qator yetarli.

**Bog'lanishlar**: `department` (M-1, ixtiyoriy).

### app_settings — Tizim sozlamalari (16-band, SINGLETON jadval)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | doim faqat bitta qator (id=1) |
| remind_time | TIME | kunlik eslatma job'i ishga tushadigan vaqt (default: 08:30) |
| default_penalty_multiplier | FLOAT | `penalty_rules.score`ga qo'llanadigan global ko'paytiruvchi (default: 1.0) |
| brigade_share_ratio | FLOAT | ishchi minus balidan brigadirga o'tadigan ulush (8.4-band, default: 0.33) |
| balls_per_day_shift | INTEGER | har N minus ball uchun to'lov kuni 1 kunga suriladi (8.5-band, default: 5) |
| created_at / updated_at | TIMESTAMPTZ | |

`f490887dee10` migratsiyasi orqali yaratilgan va bitta seed qator bilan
boshlang'ich qiymatlarga ega. Har doim `services/settings_service.py` orqali
(xotirada keshlangan holda) o'qiladi/yangilanadi — jadvalga to'g'ridan-to'g'ri
murojaat qilinmaydi. `remind_time` o'zgarganda `jobs/reminder_job.py`ning
APScheduler jadvali (`main.py`da ro'yxatdan o'tkazilgan) `scheduler.reschedule_job()`
orqali darhol qayta rejalashtiriladi. Faqat `Role.ADMIN`/`Role.SUPERVISOR`
o'zgartira oladi (`middlewares/auth.py: RoleAccessMiddleware`).

`BASE_PAYMENT_DAY` (8.5-banddagi bazaviy to'lov kuni, 15) bu ro'yxatda YO'Q —
`penalty_service.py`da hali konstanta bo'lib qolmoqda, chunki so'ralgan 4 ta
sozlama ro'yxatiga kirmagan edi.

## Munosabatlar sxemasi (qisqacha)

```
departments 1───M brigades M───1 employees (brigadier_id, ixtiyoriy)
departments 1───M employees
departments 1───M tasks (current_department_id)
departments 1───1 departments (next_department_id, ixtiyoriy — bosqich zanjiri)

tasks 1───M task_assignments M───1 employees
tasks 1───M stop_logs M───1 employees
tasks 1───1 tasks (previous_task_id, ixtiyoriy — bosqich zanjiri)

employees 1───M kpi_logs
```

## Hali aniqlanmagan / keyingi bosqichda qo'shiladigan jadvallar

- `clients`, `leads`, `call_logs` — 13-band, sotuv CRM moduli uchun (Ezza/Melores).
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
