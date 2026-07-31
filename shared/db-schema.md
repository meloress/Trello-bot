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
| starts_stopped | BOOLEAN | default: false (Fasad sex TZ: buyurtma STOPPED holatda ochilishi, `2ec88464a4f8` migratsiyasi). `True` bo'lsa, `task_service.create_task()` yangi vazifani `ACTIVE` o'rniga `STOPPED` holatda yaratadi va bir vaqtda `StopLog` qatorini ham yozadi ("joy tayyor bo'lishini kutmoqda") — shu qator bo'lmasa `timer_service.resume_task()` ishlamas edi. **`f3a7c1d9e4b6` migratsiyasidan boshlab bir xil xatti-harakat `task_service.activate_pending_stage()`da ham ishlaydi** — mid-chain bo'lim (masalan "Sklad") ham stage boshlanganda darhol STOPPED holatga o'tadi, oldin bu faqat buyurtmaning ENG BIRINCHI bosqichida ishlar edi. Mini App'ning `POST /admin/departments` / `POST /admin/departments/{id}` orqali sozlanadi |
| stopped_auto_resume_after_hours | INTEGER, NULL | default: NULL (`f3a7c1d9e4b6` migratsiyasi). Faqat `starts_stopped=True` bo'lgan bo'limlar uchun ma'noli. NULL = standart — Stop cheksiz kutadi, qo'lda `resume_task()` kerak (masalan "Zakaz tushdi": haqiqiy "joy tayyor" signalini kutadi). Sonli qiymat berilsa (masalan Sklad: `24`) — `jobs/overdue_watch_job.py`ning `_process_stopped_auto_resume()` qismi (soatiga bir marta) faol `StopLog.stopped_at`dan shu necha soat o'tgan STOPPED vazifalarni muammo signali bo'lmagan deb hisoblab avtomatik `resume_task(employee_id=None)` orqali davom ettiradi. Hozircha alohida UI ekrani yo'q — faqat `POST /admin/departments/{id}` orqali (departments.py'dagi boshqa raw-DB config ustunlari kabi) |
| requires_join | BOOLEAN | default: false (Fasad sex TZ, Phase 3 fork/join, `b7c1e4f9a83d` migratsiyasi). `True` = konvergensiya (join) bo'limi — bir nechta parallel tarmoq shu bo'limga qaytib qo'shiladi. `task_service.advance_task_stage()` bu bo'limga o'tishdan oldin BARCHA qardosh tarmoqlar (bir xil `tasks.previous_task_id`ni ulashadigan qatorlar) COMPLETED bo'lishini kutadi — oxirgi tarmoq tugaganda yagona join bosqichi yaratiladi; undan oldingi tarmoqlar `None` qaytaradi (bosqich hali yaratilmaydi). Mini App'ning `POST /admin/departments/{id}` orqali sozlanadi |
| module | VARCHAR(20) | default: `'mebel'` (Fasad sex TZ, Phase 0 — Mini App modul almashtirgichi, `d33c76d946db` migratsiyasi). Shu bo'lim qaysi ishlab chiqarish moduliga tegishli — `"mebel"` (asosiy, standart) yoki `"fasad_sex"` (yangi, parallel zanjir); enum/CHECK emas, oddiy VARCHAR (repo konvensiyasi — 3-modul kelajakda qo'shilsa, cheklovsiz kengayadi). `miniapp/api/common.py`'ning `GET /me`'si `available_modules`'ni shu ustunga qarab hisoblaydi (rol + `employee.department_id` bo'yicha) — frontend shu ro'yxatga qarab modul tanlash ekranini ko'rsatadi/o'tkazib yuboradi |
| factory_name | VARCHAR(100), NULL | Fasad sex TZ §9 "ikkinchi zavod" (`3137620903a2` migratsiyasi). `module`dan MUSTAQIL — `module` qaysi ishlab chiqarish TIZIMIga (mebel/fasad_sex), `factory_name` esa qaysi jismoniy ZAVOD/FILIALga tegishli ekanini belgilaydi (2+ jismoniy joylashuv statistikasi aralashmasligi uchun, hech biri ikkinchisidan hisoblanmaydi). NULL = hali belgilanmagan. `stats_service.get_monthly_stats(factory_name=...)` ixtiyoriy filtr parametri sifatida ishlatadi (`Employee.department_id -> Department.factory_name` join, `None` — filtrsiz, avvalgidek). Mini App'ning `POST /admin/departments` / `POST /admin/departments/{id}` orqali sozlanadi (`GET /admin/stats?factory_name=` orqali o'qiladi) — hozircha alohida UI/zavod-tanlash ekrani yo'q |
| stop_target_list_id | VARCHAR(50), NULL | Fasad sex TZ, Phase 5 (`c8a2e6f31b90` migratsiyasi). NULL = standart xatti-harakat — `timer_service.stop_task()`/`resume_task()` faqat DB status (`STOPPED`/`ACTIVE`) o'zgartiradi, karta joyidan qo'zg'almaydi (mavjud mebel liniyasidagi HAMMA bo'lim uchun shu). Sozlangan bo'lsa: Stop bosilganda karta shu Trello ro'yxatiga (masalan "stopda") ko'chiriladi, Resume bosilganda esa `trello_list_id`ga (bu ustunga EMAS) qaytariladi — ikkalasi ham ikkinchi-darajali effekt (try/except-log-only, DB yozuvidan KEYIN, muvaffaqiyatsizlik Stop/Resume amalini bloklamaydi). Mini App'ning `POST /admin/departments/{id}` orqali sozlanadi — hozircha alohida UI ekrani yo'q, qaysi bo'limlarda yoqilishi keyingi config-only qadam |
| default_sla_hours | INTEGER, NULL | SPEC.md §5.1 (`c7f2a91b0d48` migratsiyasi). Bosqichning standart muddati soatda: buyurtma shu bo'limga o'tgan ANIQ paytdan boshlab `deadline = entered_at + default_sla_hours` avtomatik hisoblanadi (`task_service._spawn_pending_stage()`), ya'ni taymer nazoratchi tugmani bosgan paytdan emas, buyurtma haqiqatda bosqichga kirgan paytdan ketadi (TZ aynan shuni talab qiladi). Bosqich baribir `PENDING_SETUP` bo'lib qoladi — u IKKI narsani kutadi (muddat VA xodim), SLA faqat birinchisini yechadi; `activate_pending_stage(deadline=None)` esa oldindan hisoblangan qiymatni saqlaydi. NULL = SLA yo'q, muddat butunlay qo'lda kiritiladi (eski xatti-harakat). **Mebel modulida umuman o'qilmaydi** — u yerda muddat Trello kartadan/list nomidan keladi. Mini App'ning bo'lim tahrirlash ekrani orqali sozlanadi |
| daily_quota_orders | INTEGER, NULL | SPEC.md §5.2 (`d5b83e10c9a7`): kuniga nechta buyurtma "normada" hisoblanadi (chizish bosqichi: 5). Navbat qoidasi FAQAT bu ustun VA `sla_over_quota_hours` ikkalasi ham sozlanganda yoqiladi. "Kun ichidagi tartib" — shu bo'limda shu KALENDAR kunda (Toshkent, UTC sutkasi emas) yaratilgan ORDER bosqichlari soni (`task_repo.count_created_in_department_since()`) |
| sla_urgent_hours | INTEGER, NULL | SPEC.md §5.2: `tasks.is_urgent=true` buyurtma navbatdan qat'i nazar shuncha soat oladi (24). NULL = srochniy buyurtma ham oddiy qoidaga tushadi |
| sla_over_quota_hours | INTEGER, NULL | SPEC.md §5.2: kunlik normadan oshgan buyurtma uchun muddat (72). "Norma ichida"gi qiymat uchun alohida ustun YO'Q — u `default_sla_hours`ning o'zi (48), shuning uchun qoida o'chirilganda xatti-harakat avtomatik oddiy SLA'ga qaytadi |
| sla_block_id | VARCHAR(50), NULL | SPEC.md §5.3 "blok SLA": bir xil qiymatga ega KETMA-KET bo'limlar bitta blok (shkurka + kraska + malyarka = 15 kun). Blok ichidagi bosqichlar o'z muddatini olmaydi — muddat blokka KIRGANDA bir marta qo'yiladi va blokdan chiqquncha `task_service.resolve_stage_deadline()` orqali ko'chib boradi ("ichida erkin harakatlanish mumkin"). Jarima/bonus ham faqat blokdan CHIQISHDA hisoblanadi (`penalty_service._is_inside_sla_block()`), aks holda bitta kechikish uchun blokdagi har bosqich alohida jarima yozgan bo'lardi. Chiqish = `next_department_id` yo'q YOKI keyingi bo'lim boshqa blokda. NULL = bo'lim hech qanday blokka kirmaydi (standart) |
| telegram_chat_id | VARCHAR(50), NULL | SPEC.md §8 (`e9c04a7f3b62`): "har sexning o'z Telegram guruhi bor (fasad guruhi, krovat guruhi va h.k.)". Yangi vazifa biriktirilganda (`notify_task_started`) va muddat o'tganda (`notify_task_overdue`) shaxsiy xabar bilan bir qatorda shu guruhga ham yuboriladi. Bot guruhga a'zo qilingan bo'lishi kerak. VARCHAR (INTEGER emas) — supergroup ID'lari (`-100...`) int32'ga sig'maydi va Telegram API matn qiymatni ham qabul qiladi. Guruh xabariga Mini App tugmasi QO'YILMAYDI (`web_app` tugmasi faqat shaxsiy chatda ochiladi). NULL = guruh yo'q, hech narsa yuborilmaydi |
| created_at / updated_at | TIMESTAMPTZ | |

**Bog'lanishlar**: `brigades` (1-M), `employees` (1-M), `tasks` (1-M, `current_department_id` orqali), `next_department` (M-1, o'z-o'ziga, ixtiyoriy), `department_fork_targets` (1-M, fork nuqtasi sifatida).

### department_fork_targets — Fork zanjiri (Fasad sex TZ, Phase 3)
Fork/join zanjiri uchun (`b7c1e4f9a83d` migratsiyasi). `next_department_id` bitta bola (chiziqli zanjir) beradi — bu jadval esa BITTA bo'limni N parallel tarmoqqa BO'LADI (fork). Fork/join FAQAT shu jadvalga qatori bor bo'limlar uchun ishlaydi; qolgan hamma bo'lim `next_department_id` bo'yicha o'zgarishsiz ishlaydi. `advance_task_stage()` joriy bo'lim uchun bu jadvalni BIRINCHI tekshiradi: qator bor bo'lsa — har bir target uchun bitta `PENDING_SETUP` bosqich yaratiladi (hammasi bir xil `previous_task_id`ni ulashadi, Trello karta KO'CHMAYDI — fork nuqtasi list'ida qoladi), `list[Task]` qaytaradi.
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| department_id | FK -> departments.id (`fk_department_fork_targets_department_id`) | NOT NULL; fork NUQTASI (masalan "Fayl yig'ish") |
| target_department_id | FK -> departments.id (`fk_department_fork_targets_target_department_id`) | NOT NULL; undan chiqadigan parallel tarmoqdan biri (masalan "Korpus qismi") |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE(department_id, target_department_id)` (`uq_department_fork_target`). Mini App'ning `GET/POST /admin/departments/{id}/fork-targets` orqali boshqariladi (POST = to'liq almashtirish: hammasini o'chir, yangisini qo'sh). Frontend UI hali yo'q. Haqiqiy Fasad sex zanjiri 2026-07-24da yaratildi (`.claude/nazorat-trello/01-haqiqiy-zanjir-yaratish.md`) — "Fayl yig'ish" (fork nuqtasi) -> "Korpus qismi"/"Ichki qism"/"Fasad qismi" (3 target), "Korpus sexi (upakovka)" (`requires_join=True`) shu uchtasini kutadi.

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
| manager_id | FK -> employees.id, NULL | SPEC.md §7/§8 (`e9c04a7f3b62`, o'z-o'ziga FK `fk_employees_manager_id`): bevosita rahbar. Bo'ysunuvchiga JARIMA (manfiy ball) yozilganda (`notify_penalty_applied`) va uning vazifasi muddatidan kechikkanda (`notify_task_overdue` -> `_add_managers`) rahbar ham xabar oladi; bonus (musbat ball) uchun yuborilmaydi. `department_id`dan MUSTAQIL — bo'lim "qayerda ishlaydi", `manager_id` "kimga hisobot beradi". O'z-o'ziga ishora qilish `POST /admin/employees/{id}`da rad etiladi; `_add_managers` bir POG'ONA o'qiydi (rahbarning rahbari qo'shilmaydi — `ponytail:` izohiga qarang). NULL = rahbar belgilanmagan |
| daily_report_required | BOOLEAN | ⚠️ **ISHLATILMAYDI** — Fasad sex TZ, Phase 8 (`83d73ef87edc`). Kunlik rasm/video hisobot funksiyasi 2026-07-31'da koddan butunlay o'chirilgan; bu ustun DB'da qoldi, lekin `Employee` modelida YO'Q va hech qayerdan o'qilmaydi/yozilmaydi (`server_default='false'`) |
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
| misc_category | VARCHAR(20), NULL | Fasad sex TZ, Phase 9 (`e1a4b8f36c02` migratsiyasi). MISC vazifalar uchun ixtiyoriy kategoriya (ofis/Fasad sex/o'rnatuvchi/payvandchi, `utils/enums.MiscCategory`). ORDER'da har doim NULL — faqat `task_type=MISC` qatorlarida ma'noli, funksiya qo'shilishidan oldingi eski MISC qatorlar ham NULL bo'lishi mumkin |
| trello_last_seen_list_id | VARCHAR(50), NULL | Mebel Trello-first sync (`77a6fe7328cd` migratsiyasi, 2026-07-26). `jobs/trello_ingest_job.py`ning oxirgi muvaffaqiyatli poll paytidagi karta `idList`i — bosqich o'tishi/qayta-tayinlashni aniqlash uchun "oxirgi ko'rilgan holat". Faqat `module="mebel"` vazifalarida to'ldiriladi, boshqa hamma qatorda har doim NULL |
| trello_last_seen_member_ids | JSON, NULL | Yuqoridagisi bilan bir xil sync uchun — oxirgi ko'rilgan Trello karta a'zo-ID'lari ro'yxati (brigadir almashinuvini aniqlash uchun) |
| trello_last_polled_at | TIMESTAMPTZ, NULL | Diagnostika: `trello_ingest_job` bu qatorni oxirgi marta qachon ko'rgani |
| advanced_without_finish_claim_at | TIMESTAMPTZ, NULL | Mebel Trello-first sync: karta claim tasdiqlanmasdan (yoki umuman yuborilmasdan) keyingi bo'lim ro'yxatiga qo'lda ko'chirilganda birinchi marta belgilanadi — zanjir baribir davom etadi (jismoniy voqelik: karta allaqachon ko'chgan), lekin eski bosqich "tasdiqlanmagan" holatda qoladi va `overdue_watch_job`ning eskalatsiya bosqichlariga signal beradi |
| stopped_seconds_total | INTEGER, NOT NULL | default: 0 (SPEC.md §6, `c7f2a91b0d48` migratsiyasi). "Stop" holatida o'tgan JAMI vaqt soniyada. Har `resume_task()`da o'sha to'xtash davomiyligi bu yerga qo'shiladi va SHU QADAR `tasks.deadline` ham oldinga suriladi — taymer haqiqatda muzlaydi, ishchi kutilgan davr uchun jarima olmaydi (TZ §6.1). Statistikada ham shu qiymat ish vaqtidan chiqariladi (TZ §6 oxirgi band). **Faqat `fasad_sex` bo'limlarida yangilanadi** — mebelda "Stop" muddatga umuman tegmaydi (u yerda muddat Trello kartadan keladi va har pollda qayta o'qiladi, surish ingest bilan urishib qolardi), guard `timer_service._paused_shift()`da |
| is_urgent | BOOLEAN, NOT NULL | default: false (SPEC.md §5.2, `d5b83e10c9a7`). "Srochniy" buyurtma — bo'limda navbat qoidasi sozlangan bo'lsa, bunday buyurtma navbatdan qat'i nazar `departments.sla_urgent_hours` oladi. Butun buyurtmaga tegishli, bitta bosqichga emas: `client_id`/`trello_checklist_id` kabi zanjir bo'ylab `_spawn_pending_stage()` orqali ko'chadi. Mini App'ning yangi buyurtma formasidagi belgi orqali qo'yiladi |
| last_overdue_reminder_at | TIMESTAMPTZ, NULL | SPEC.md §5.4 (`c7f2a91b0d48` migratsiyasi): "kechikish davom etsa, har M soatda takroriy eslatma". Oxirgi TAKRORIY kechikish eslatmasi yuborilgan payt (`overdue_watch_job._process_overdue_repeat_reminders`). NULL = hali takror yuborilmagan — bunda hisob `deadline`ning o'zidan boshlanadi, ya'ni birinchi takror muddatdan `app_settings.overdue_repeat_hours` keyin ketadi (birinchi "muddat o'tdi" xabari alohida, `_process_newly_overdue`da bir marta). Faqat `fasad_sex` |
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

**Fork/join (Fasad sex TZ, Phase 3)**: yuqoridagi chiziqli oqim `advance_task_stage()`da
fork/join qo'shimchasi bilan kengaytirildi (qaytish turi endi `Task | list[Task] | None`),
lekin fork/join'ga KIRMAGAN har qanday bo'lim uchun xatti-harakat AYNAN eskicha
qoladi. Joriy bo'lim `department_fork_targets` jadvalida qatorga ega bo'lsa (fork
NUQTASI) — har target uchun bitta `pending_setup` qator yaratiladi (hammasi bir xil
`previous_task_id` = fork nuqtasi task id'si, bir xil `trello_card_id`), Trello karta
KO'CHMAYDI (bitta karta N list'da tura olmaydi — u fork nuqtasi list'ida qoladi,
parallel jarayon checklist orqali ko'rinadi), `list[Task]` qaytadi. Keyingi bo'lim
`requires_join=True` bo'lsa (konvergensiya) — o'sha fork nuqtasidan chiqqan qardosh
tarmoqlar (`task_repo.list_by_previous_task_id()`) hammasi COMPLETED bo'lgunча har
tarmoq `None` qaytaradi; OXIRGI tarmoq tugaganda esa oddiy chiziqli yo'l ishlaydi
(karta join bo'limi list'iga ko'chadi, yagona join qatori yaratiladi). Qardosh
qidiruv har fork tarmog'i join'gача AYNAN bitta bo'lim chuqurlikda deb faraz qiladi
(`ponytail:` izohi — ko'p bosqichli sub-zanjir kerak bo'lsa `fork_root_task_id`ni
oldinга ko'chirish kerak). Checklist "Bosqichlar" ham chiziqli emas, BFS + `visited`
to'plami bilan quriladi (`_collect_department_chain_names()`) — fork fan-out'ni,
join fan-in'ni (bir marta) to'g'ri ochadi; fork YO'Q zanjir uchun eski chiziqli
natija bilan bayt-mos.

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

### task_claims — Rahbar tasdig'i orqali claim (mebel Trello-first sync, `3c977b3a0d86` migratsiyasi, 2026-07-26)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| task_id | FK -> tasks.id, NOT NULL | qaysi bosqich uchun so'rov |
| employee_id | FK -> employees.id, NOT NULL | tugmani bosgan ishchi |
| action_type | VARCHAR (Enum `ClaimActionType`, `native_enum=False`) | `pause` / `finish` |
| status | VARCHAR (Enum `ClaimStatus`, `native_enum=False`), default `pending` | `pending` / `approved` / `rejected` |
| claimed_at | TIMESTAMPTZ, NOT NULL | ishchi tugmani bosgan ANIQ vaqt — tasdiqlansa shu vaqt `tasks.finished_at`/`stop_logs.stopped_at`ga o'tadi, rahbar tasdiqlagan vaqt EMAS (bu jadvalning butun maqsadi shu) |
| reason | TEXT, NULL | `pause` uchun majburiy (servis darajasida tekshiriladi), `finish` uchun ixtiyoriy |
| reviewed_by_employee_id | FK -> employees.id, NULL | tasdiqlagan/rad etgan rahbar (SUPERVISOR/ADMIN) |
| reviewed_at | TIMESTAMPTZ, NULL | |
| rejection_note | TEXT, NULL | ishchiga ko'rsatiladi |
| last_reminder_stage | INTEGER, default 0 | eslatma eskalatsiyasi uchun (0 = hali yuborilmagan, 1/2/3 = +2/+6/+24 soat bosqichlari) |
| last_reminder_sent_at | TIMESTAMPTZ, NULL | |
| created_at / updated_at | TIMESTAMPTZ | |

Faqat `module="mebel"` vazifalarida ishlatiladi (`fasad_sex` hamon Mini App'ning
`/tasks/{id}/stop`/`/finish` orqali darhol ta'sir qiladigan eski yo'ldan
foydalanadi). Bir vaqtda faqat bitta `pending` claim (qisman UNIQUE indeks,
`task_id` bo'yicha, `status='pending'` shartida). `services/claim_service.py`:
`submit_claim()` shu qatorni yaratadi (hech qanday `tasks`/`stop_logs`
mutatsiyasisiz); `approve_claim()` `timer_service.finish_task()`/`stop_task()`ni
`claimed_at`ni aniq uzatib chaqiradi (shundan keyingina `penalty_service`
odatdagidek ishlaydi); `reject_claim()` faqat `status=rejected` qiladi, hech
qanday task mutatsiyasi yo'q — vazifa avvalgidek davom etadi, kechikish oddiy
tarzda hisoblanaverdi (maxsus "rad etish jarimasi" yo'q).

`UNIQUE(task_id, employee_id)` — bitta xodim bitta vazifaga faqat bir marta biriktiriladi.

**Bog'lanishlar**: `task` (M-1), `employee` (M-1).

### task_sellers — Vazifa <-> Sotuvchi (M-to-M)
Fasad sex TZ, Phase 5 (`c8a2e6f31b90` migratsiyasi). `task_assignments` bilan
BIR XIL shakl, lekin ma'nosi boshqa — bu KPI/timer tayinlash EMAS, faqat
"Stop" bosilganda qo'shimcha xabar oladigan sotuvchi(lar) ro'yxati
(`notification_service.notify_task_stopped()` bu jadvalni ham o'qiydi va
mavjud stopper/brigadir/nazoratchi-admin ro'yxatiga `employee_id` bo'yicha
deduplikatsiya qilib qo'shadi). `task_service.create_task()`ning
`seller_ids` parametri orqali yoziladi — bittaga ko'pi bilan 3 ta sotuvchi
(`ValueError`, `create_misc_task`ning 3 xodim chegarasi bilan bir xil naqsh).
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| task_id | FK -> tasks.id | |
| employee_id | FK -> employees.id | |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE(task_id, employee_id)`.

**Bog'lanishlar**: yo'q (oddiy ko'p-ko'pga jadval, ORM relationship'siz —
`TaskSellerRepository.list_by_task()` orqali to'g'ridan-to'g'ri so'raladi).

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
| daily_quota_points_per_worker | INTEGER | Fasad sex TZ, Phase 6 (`7b3d4bf8afe4`): kunlik norma — har ISHCHI kuniga shuncha "punkt" ishlab chiqarishi kutiladi ("5 punkt ≈ 100 kv.m", default: 5). FAQAT stats/dashboard uchun (`stats_service.get_capacity_vs_actual()`) — timer/jarima sifatida MAJBURIY QILINMAYDI, `penalty_service.py`ga tegishli emas |
| speed_tier_schedule | JSON | Fasad sex TZ, Phase 7 (`a3f7c9d02b41`): tezlik-darajali to'lov taklifi jadvali — `[{"max_days": N, "tier": "<nom>", "pay_multiplier": X}, ...]`. Default: bo'sh ro'yxat (admin to'ldirmaguncha xususiyat harakatsiz) |
| daily_report_time | VARCHAR(5) | ⚠️ **ISHLATILMAYDI** — Fasad sex TZ, Phase 8 (`83d73ef87edc`). Kunlik hisobot funksiyasi 2026-07-31'da o'chirilgan; ustun DB'da qoldi, lekin `AppSetting` modelida ham, `AppSettingsSnapshot`da ham YO'Q (`server_default='09:00'`) |
| deadline_warning_hours | INTEGER | SPEC.md §5.4 (`c7f2a91b0d48`): muddat tugashiga shuncha soat qolganda ogohlantirish yuboriladi (default: **4**). Avval bu qiymat `task_repo.list_deadline_approaching()`da 24 soat qilib kodga tikilgan edi ("1 kun qoldi") — TZ esa uni sozlanuvchan, standarti 4 soat deb belgilaydi. `jobs/overdue_watch_job.py._process_deadline_approaching()` o'qiydi |
| penalize_all_assignees | BOOLEAN | default: **true** (SPEC.md §7, `e9c04a7f3b62`): "bir bosqichda 2 kishi biriktirilgan bo'lsa — ikkalasiga ham yoziladi (yoki konfig bo'yicha faqat asosiy mas'ulga). Sozlanadigan bo'lsin". `true` = bugungi xatti-harakat, hamma javobgarga. `false` = faqat BIRINCHI javobgarga (tayinlanish tartibi bo'yicha — u "asosiy mas'ul"), brigadir ulushi ham o'sha bittasidan hisoblanadi (`penalty_service._write_scores_for_employees(penalize_all=...)`). Mini App sozlamalar ekranida belgi (checkbox) sifatida — matn maydoni emas |
| overdue_repeat_hours | INTEGER | SPEC.md §5.4 (`c7f2a91b0d48`): "kechikish davom etsa, har M soatda takroriy eslatma" (default: **12**). `0` = takroriy eslatma o'chirilgan (yuqoridagi ustundan farqli, bu yerda nol haqiqiy va foydali qiymat — validatsiya `>= 0` ni qabul qiladi). `jobs/overdue_watch_job.py._process_overdue_repeat_reminders()` o'qiydi, faqat `fasad_sex` vazifalariga qo'llanadi |
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
RoleAccessMiddleware`). 11 ta skalyar qiymat (yuqoridagi jadval, `lead_follow_up_
threshold_days` va `daily_quota_points_per_worker` shu jumladan) `/settings`
orqali xuddi shu yo'l bilan tahrirlanadi. `sales_board_lists` bundan mustasno — `departments.trello_list_id`
kabi bot UI orqali EMAS, to'g'ridan-to'g'ri bazada sozlanadi (haqiqiy Ezza/
Melores Trello boardlari yaratilgach).

`BASE_PAYMENT_DAY` (8.5-banddagi bazaviy to'lov kuni, 15) bu ro'yxatda YO'Q —
`penalty_service.py`da hali konstanta bo'lib qolmoqda, chunki so'ralgan 4 ta
sozlama ro'yxatiga kirmagan edi.

### daily_report_submissions — ⚠️ KOD TOMONDAN O'CHIRILGAN (2026-07-31)

> **Bu jadval DB'da bor, lekin unga murojaat qiladigan hech qanday kod
> qolmagan.** Rahbar talabiga ko'ra ("kunlik rasm/video umuman kerak
> emas") butun funksiya koddan olib tashlandi: `services/daily_report_service.py`,
> `jobs/daily_report_job.py`, `handlers/common/daily_report.py`, model va
> repository fayllari, `GET /admin/daily-reports` route'i va Mini App
> ekrani. `employees.daily_report_required` va `app_settings.daily_report_time`
> ustunlari ham modellardan olib tashlandi (ikkalasida `server_default`
> bor, shuning uchun xavfsiz) — lekin DB'da qoldi.
>
> O'chirish xavfsiz edi: o'sha paytda jadvalda **0 ta yozuv**, bayroq
> yoqilgan **0 ta xodim** bor edi. Bu 8.6-band "Moliyaviy takliflar"
> o'chirilishi (2026-07-27) bilan bir xil naqsh — jadval/ustunlarni
> haqiqatan tashlash uchun alohida so'ralgan Alembic migratsiyasi kerak.
>
> Quyidagi tavsif tarixiy — funksiya qayta kerak bo'lsa ma'lumotnoma
> sifatida qoldirildi.

<details><summary>Tarixiy tavsif (funksiya ishlagan paytdagi)</summary>

| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| employee_id | FK -> employees.id | |
| report_date | DATE | hisobot QAYSI kalendar kun UCHUN (Toshkent vaqti) — jo'natilgan payt emas |
| file_id | VARCHAR(200) | Telegram'ning `photo`/`video` fayl identifikatori — tizimda fayl saqlash qatlami yo'q, faqat shu satr saqlanadi |
| submitted_at | TIMESTAMPTZ | oxirgi yuborilgan payt |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE(employee_id, report_date)` (`uq_daily_report_submissions_employee_date`,
`83d73ef87edc` migratsiyasi) — bitta xodim uchun bitta kunga bitta yozuv,
qayta yuborilsa `services/daily_report_service.submit_daily_report()` mavjud
qatorni YANGILAYDI (upsert), yangi qator yaratmaydi. **FAQAT kuzatuv** — bu
jadval hech qanday jarima/ball hisobiga ta'sir qilmaydi (`penalty_service.py`ga
ATAYLAB tegilmagan; TZning o'zi ham bu masalada ochiq savol qoldirgan).
Yig'ish/so'rov oqimi to'liq chat-based (`handlers/common/daily_report.py`,
`/mijoz`dan keyingi ikkinchi ataylab chat-only istisno — Telegram'ning tabiiy
kamera/galereya tugmasi Mini App WebView fayl-inputidan qulayroq), Mini App
faqat `GET /admin/daily-reports` orqali muvofiqlik holatini KO'RSATADI.

**Bog'lanishlar**: `employee` (M-1).

</details>

### financial_suggestions — Moliyaviy javobgarlik TAKLIFLARI (8.6-band, 3-bosqich)
| Ustun | Tur | Izoh |
|---|---|---|
| id | PK | |
| task_id | FK -> tasks.id | qaysi bosqich-qatoriga tegishli |
| kind | VARCHAR | `wage_deduction` (1-qoida), `advance_waiver` (2-qoida) yoki `speed_tier_bonus` (Fasad sex TZ, Phase 7 — `a3f7c9d02b41` migratsiyasi `alter_column` bilan enum ro'yxatini kengaytirdi, VARCHAR uzunligi 14->qiymatga mos avtomatik o'sdi) |
| status | VARCHAR | doim `pending_manager_review` bilan yaratiladi — tizim hech qachon o'zi `approved`/`rejected` qilmaydi, bu BOSHQA (hali qurilmagan) modul ishi |
| applicable | BOOLEAN | qoida shu holatga tatbiq etiladimi |
| stage_duration_days | INTEGER, NULL | `wage_deduction`: bosqich necha kun davom etgani |
| amount_withheld_by_customer | FLOAT, NULL | `wage_deduction`: mijoz ushlab qolgan summa — HAR DOIM qo'lda kiritiladi (tizimda moliya moduli yo'q), avtomatik bayroqlashda `NULL` ("kutilmoqda") |
| suggested_deduction_amount | FLOAT, NULL | `wage_deduction`: taklif qilingan ushlab qolish summasi = `amount_withheld_by_customer * 0.5` (dumaloqlashtirilmagan) |
| advance_percent_paid | INTEGER, NULL | `advance_waiver`: qo'lda kiritilgan avans foizi |
| order_total_value | FLOAT, NULL | `advance_waiver`: qo'lda kiritilgan buyurtma summasi |
| waived_amount | FLOAT, NULL | `advance_waiver`: kechiriladigan summa = `order_total_value * (advance_waiver_percent/100)` |
| speed_tier | VARCHAR(50), NULL | Fasad sex TZ, Phase 7 (`a3f7c9d02b41` migratsiyasi). `speed_tier_bonus`: `app_settings.speed_tier_schedule`dan mos kelgan tezlik darajasi nomi (`financial_service.calculate_speed_tier_bonus()`); mos keladigan daraja topilmasa ham baribir aniqlanadi |
| suggested_pay_amount | FLOAT, NULL | Fasad sex TZ, Phase 7 (`a3f7c9d02b41` migratsiyasi). `speed_tier_bonus`: taklif qilingan haq = `base_pay_amount * pay_multiplier` — `base_pay_amount` berilmasa (hali qo'lda kiritish yo'q) `NULL` qoladi, faqat `speed_tier`ning o'zi aniqlanadi |
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
