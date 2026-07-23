# Fasad sex — ikkinchi ishlab chiqarish moduli

TZ bandi: `Nazorat_Trello_Bot_TZ_v1.2_sxemalar_bilan.pdf` (butun hujjat).
Holat: BOSHLANDI — quyidagi bosqichlar mustaqil ravishda amalga oshiriladi,
har biri o'z checkbox'i bilan kuzatiladi.

## Kontekst

Mavjud bot mebel ishlab chiqarish zanjirini boshqaradi. Yangi TZ — shu bilan
PARALLEL, alohida "Fasad sex" ishlab chiqarish liniyasini tasvirlaydi.
Foydalanuvchi talabi: yangi bot/deploy emas, mavjud dvigatel (Role/Employee/
Department-Task zanjiri/task_service/timer_service/penalty_service/Mini App)
qayta ishlatiladi, Fasad sex alohida `departments` daraxti + Mini App'da
aniq ajratilgan modul sifatida qo'shiladi (tugma bosib ikki tizim orasida
almashish mumkin).

Kod chuqur tekshirilgach (Explore agentlar + to'g'ridan-to'g'ri fayl o'qish)
tasdiqlangan arxitektura qarorlari:
1. **Trello tuzilishi**: bitta umumiy list + mas'ul-xodim maydoni (mavjud
   dvigatel bilan bir xil) — har-xodim-uchun-alohida-list QURILMAYDI.
2. **Fork/join**: Fayl yig'ish → Korpus/Ichki/Fasad qismlarga AJRALISH →
   Korpus sexida qayta BIRLASHISH — TO'LIQ arxitektura (soddalashtirilgan
   v1 emas).
3. **Kunlik rasm/video hisobot** — rejaga kiritilgan, jarima qoidasisiz,
   faqat kuzatuv (compliance).
4. **Ikkinchi zavod**: `departments`ga yengil matn tegi (`factory_name`) —
   bloklangan Ping/SaaS multi-tenant (`08-saas-tayyorgarlik.md`) bilan
   ARALASHTIRILMAYDI.
5. **Mini App navigatsiyasi**: kirishda "qaysi tizim" tanlash ekrani
   (`departments.module` tegi), Profil ichidan almashtirish — pastki
   tab-bar hech qachon ikki tizimni bitta ro'yxatda aralashtirmaydi.

TZning o'zi 13/14-bo'limlarida 17 ta atama/savolni ochiq deb belgilagan —
bularning barchasi `09z-fasad-sex-ochiq-savollar.md`da kuzatiladi, kod
ularni taxmin qilmaydi.

## Bosqichlar (checklist)

- [x] **Phase 0 — Mini App'da ikki tizim almashtirgichi.** BAJARILDI
  (`ccafb99`, review: Approved). `fasad_sex` tab to'plami hozircha
  placeholder (`screenAdminHome`/`screenProfile` qayta ishlatiladi, haqiqiy
  Fasad sex ekranlari hali yo'q) — ESLATMA: placeholder ADMIN-only
  endpoint'larga tayanadi, shu tufayli `fasad_sex` bo'limiga ADMIN/
  SUPERVISOR'dan boshqa rol (ishchi/brigadir) tayinlanishidan OLDIN, real
  Fasad sex bosh sahifa ekrani (keyingi bosqichlarda) qurilishi kerak —
  aks holda 403 xatosi ko'rinadi.
  Yangi `departments.module: VARCHAR(20) NOT NULL DEFAULT 'mebel'`.
  `GET /me`ga `available_modules`. Frontend: `screenModuleChooser()`,
  `tabDefsForRole(role, module)` ikkinchi parametr, Profil'da "🔄 Tizimni
  almashtirish". Bitta modulli xodimlar chooser'ni ko'rmaydi.
- [x] **Phase 1 — Ikkinchi zavod tegi.** BAJARILDI (`7f0a692`, review:
  Approved). Minor: bo'sh-satr `?factory_name=` hozircha filtr sifatida
  o'qiladi (hozircha frontend yo'q, zararsiz — kelajakda UI qo'shilganda
  `factory_name or None` guard qo'shish kerak). Yangi `departments.factory_name:
  VARCHAR(100) NULL`. `stats_service.py`ga filtr parametri. `GET
  /admin/stats`ga query param. (`module`dan MUSTAQIL o'lchov — factory_name
  bir modul ICHIDAGI jismoniy filial farqi.)
- [x] **Phase 2 — Department admin CRUD + umumiy bosqich qo'shish + Kontrol
  + STOPPED holatda ochilish.** BAJARILDI (`7301dcd`, review: Approved,
  2 ta Minor topilma — `name` update'da trim qilinmaydi, boolean maydonlar
  update'da cast qilinmaydi — keyingi fazalar shu qatorlarga tegsa tuzatish
  kerak). `POST /admin/departments` (yaratish),
  `POST /admin/departments/{id}` (umumiy qisman-yangilash). Zanjirga
  istalgan joyga qo'shish — mavjud `POST /departments/{id}/chain` orqali,
  YANGI BACKEND KOD KERAK EMAS (tasdiqlangan). "Kontrol" — oddiy Department
  qatori, `activate_pending_stage()` allaqachon `employee_ids: list[int]`
  qabul qiladi, YANGI KOD KERAK EMAS. Yangi `departments.starts_stopped:
  BOOLEAN NOT NULL DEFAULT false` + `create_task()`ga
  `created_by_employee_id` — STOPPED holatda ochilganda darhol `stop_logs`
  qatori yoziladi (aks holda `resume_task()` ishlamay qoladi —
  `stop_repo.get_active_stop()` talab qiladi).
- [x] **Phase 3 — Fork/join zanjir arxitekturasi.** BAJARILDI (`6096e3a`,
  review: Approved — chiziqli zanjir uchun "byte-identical" talab qatorma-
  qator tekshirildi). Minor topilmalar (kelajakda diqqat qilish kerak):
  (1) join-fire idempotent EMAS — 2 ishchi bir vaqtda oxirgi 2 filialni
  tugatsa, ikkalasi ham join task yaratishi mumkin (race condition,
  hozircha real foydalanuvchi yo'q); (2) `POST /fork-targets`da input
  validatsiya yo'q (mavjud bo'lmagan department_id → 500, o'z-o'ziga fork
  bloklanmagan); (3) filial tugaganda ham `notify_client_stage_advanced`
  chiqadi (mijozga "bosqich o'tdi" degan xabar, aslida hali kutilmoqda).
  Frontend fork-target UI YO'Q (ataylab keyinga qoldirilgan). Yangi jadval
  `department_fork_targets` (`department_id`, `target_department_id FK`).
  Yangi `departments.requires_join: BOOLEAN NOT NULL DEFAULT false`.
  `task_service.advance_task_stage()` qayta yoziladi — qaytish turi
  `Task | list[Task] | None`. Birodar tasklar `previous_task_id` orqali
  aniqlanadi (yangi ustun kerak emas — filiallar bir bosqichli deb
  tasdiqlangan). `_collect_department_chain_names()` — chiziqli emas, BFS.
  Fork paytida karta join'gacha fork-nuqtasi list'ida qoladi (tasdiqlanishi
  kerak bo'lgan taxmin, ochiq savol #13'ga qarang).
- [x] **Phase 4 — Material turi shabloni (Laminoks/Eman va h.k.).**
  BAJARILDI (`3ccf8e3`, review: Approved). Schema o'zgarishi YO'Q — 3 ta
  oddiy `departments` qatori, Phase 2'ning yaratish+zanjirlash orqali.
  Faqat frontend qulaylik (bitta forma → 3 chaqiruv ketma-ketligi).
- [x] **Phase 5 — Stop mexanizmi kengaytmalari.** BAJARILDI (`5f1d970`,
  review: Approved). (a) Yangi jadval `task_sellers` (0-3
  sotuvchi/buyurtma), `notify_task_stopped()`ning mavjud recipient-yig'ish
  tsikliga qo'shildi (dublikat xabar yo'q, tekshirilgan). (b) Yangi
  `departments.stop_target_list_id: VARCHAR(50) NULL` — o'rnatilgan bo'lsa,
  Stop bosilganda karta shu list'ga ham ko'chiriladi, Resume'da orqaga
  qaytadi; `stop_target_list_id=None` bo'lgan bo'limlar uchun xatti-harakat
  o'zgarishsiz (tekshirilgan). `01-stop-trello-izoh.md`/
  `02-label-holatlari.md`ga tegilmadi. Minor: `seller_ids` ichida dublikat
  id kelsa `IntegrityError` (ValueError emas) chiqadi — hozircha real
  xavf yo'q (frontend yo'q).
- [x] **Phase 6 — Kunlik norma (5 punkt/ishchi) — faqat statistika.**
  BAJARILDI (`33cbeb5`, review: Approved). Yangi
  `app_settings.daily_quota_points_per_worker: INT NOT NULL DEFAULT 5`.
  `stats_service.get_capacity_vs_actual()` — `actual_points` yakunlangan-
  vazifa-soni proksi ekani 4 joyda (docstring x2, db-schema.md, frontend
  caption) aniq yozilgan. `penalty_service.py`ga tegilmadi (jarima QOIDASI
  EMAS talabi saqlandi).
- [x] **Phase 7 — Tezlikka qarab to'lov taklifi (speed-tier).** BAJARILDI
  (`3c4e150`, review: Approved). Yangi
  `app_settings.speed_tier_schedule: JSON NOT NULL DEFAULT '[]'` (bo'sh —
  aniq foizlar kelmaguncha inert, tekshirilgan). `financial_suggestions`ga
  `speed_tier`, `suggested_pay_amount`. Yangi pure function
  `financial_service.calculate_speed_tier_bonus()` — "taklif qiladi, hech
  qachon ijro etmaydi" pattern (idempotent, tekshirilgan). `kind` ustuni
  yangi qiymat sig'ishi uchun kengaytirildi (mavjud precedent bo'yicha).
- [x] **Phase 8 — Kunlik rasm/video hisobot (compliance).** BAJARILDI
  (`7aed2f4` + tuzatish `db00aa9`, mustaqil review: Approved — birinchi
  round "Needs fixes" chiqargan edi, sabab: bir vaqtda 2+ rasm kelsa
  (Telegram albom) upsert'da race condition, `IntegrityError` foydalanuvchiga
  chiqib ketardi; tuzatildi va qayta tekshirildi). Chat-based, `/mijoz`
  bilan bir xil sabab —
  lekin FSM emas: `daily_report_job` (`Bot`dan boshqa hech narsaga, jumladan
  `Dispatcher`/`storage`ga kirish huquqi yo'q, `reminder_job`/`report_job`
  bilan bir xil) oddiy matnli so'rov yuboradi, `handlers/common/
  daily_report.py`dagi HOLAT'siz filter (`F.photo`/`F.video` + DB'dan
  `daily_report_required=True` tekshiruvi) javobni ushlaydi. Yangi jadval
  `daily_report_submissions` (`UNIQUE(employee_id, report_date)`, upsert —
  tekshirilgan: qayta yuborish yangi qator EMAS). Yangi
  `employees.daily_report_required`, `app_settings.daily_report_time`
  (`report_time` bilan bir xil naqsh). Jarima YO'Q — `penalty_service.py`ga
  tegilmadi. Yon-topilma: `main.py`da `common_start_router`ning
  `StateFilter(None)` catch-all'i ILGARI `common_client_link_router`dan
  OLDIN ro'yxatdan o'tkazilgan edi — live aiogram repro bilan tasdiqlandi,
  bu holatda yangi/idle foydalanuvchidan kelgan `/mijoz` catch-all'ga tushib
  qolib, `client_link_router`ga UMUMAN yetib bormas edi; tartib tuzatildi
  (`common_start_router` endi eng oxirida).
- [x] **Phase 9 — Vazifa buyurish 4 toifasi (MISC kategoriya).** BAJARILDI.
  Yangi `tasks.misc_category: VARCHAR(20) NULL` + `MiscCategory` enum (4
  qiymat: office/fasad_sex/installer/welder). `create_misc_task()`ga
  ixtiyoriy `category` parametri (`None` — avvalgidek). Mini App:
  `POST /admin/misctasks` `category`ni qabul qiladi va tekshiradi (noto'g'ri
  qiymat → 400, 500 emas); `GET /misctasks` (worker) ixtiyoriy
  `?category=` filtri bilan kengaytirildi (`/leads?brand=`dagi bilan bir
  xil naqsh — admin'ning o'zida alohida MISC-ro'yxat ekrani yo'q edi, faqat
  yaratish formasi bor edi, shu sabab filtr mavjud ro'yxat — ishchining
  o'z vazifalari ekrani — ustiga qo'shildi). Frontend: yaratish formasida
  kategoriya dropdown + ro'yxat ekranida filtr dropdown, `i18n.js`
  (uz/ru) yangi kalitlar. `create_task()` (ORDER) va 3-xodim
  cheklovi/Trello'siz xatti-harakat tegilmadi (tekshirilgan).

## Ishlash tartibi

Phase 2 — ko'p keyingi bosqichlar uchun old shart (department yaratish
imkoniyati bo'lmasa, Fasad sex zanjiri umuman qurilmaydi). Phase 0 va
Phase 1 Phase 2'dan mustaqil, parallel olinishi mumkin (schema jihatidan
mustaqil ustunlar). Phase 3 — Phase 2'ga bog'liq. Phase 4 — Phase 2 va 3'ga
bog'liq (fork/join zanjiriga material shablon qo'shiladi). Phase 5-9 —
bir-biridan va Phase 2'dan boshqa hech narsaga bog'liq emas, istalgan
tartibda.

Har bir bosqich tugagach: shu ro'yxatdagi checkbox belgilanadi,
`shared/db-schema.md` yangilanadi (yangi jadval/ustun bo'lsa). Butun modul
tugagach: bu hujjat + `09z-fasad-sex-ochiq-savollar.md` (agar barcha
savollar hal bo'lgan bo'lsa) papkadan olib tashlanadi, README'dagi qator
ham.
