# 4-bosqich: Statistika/dashboard, oylik reytinglar, Telegram hisobotlar, mijoz xabarnomalari

Holat: NAVBATDA. TZda "2-etap, 4-bosqich": "Statistika/dashboard, oylik eng
yomon/eng yaxshi reytinglar, Telegram hisobotlar; mijoz xabarnomalari".

TZ manbasi: 10-band (statistika/dashboard), 11.1-band (brigadir statistikasi
— allaqachon qisman bor), 12-band (mijozlarga avtomatik xabarnoma), 4-band
(web panel — statistika ko'rinishi).

## Hozirda kodda NIMA BOR

- `services/stats_service.py` — `EmployeeStats` dataclass (completed_tasks,
  total_score, penalty_count). Uchta funksiya: `get_monthly_stats()` (barcha
  faol xodim, joriy oy), `get_brigade_monthly_stats(brigade_id)` (bitta
  brigada, joriy oy), `get_employee_weekly_stats(employee_id)` (bitta xodim,
  oxirgi 7 kun). Barchasi guruhlangan SQL so'rovlar orqali (N+1 emas).
- `handlers/admin/stats.py` — `/stats` buyrug'i, joriy oy jadvalini kod-blok
  ichida chiqaradi (eng yuqori ball, eng ko'p jarima ko'rsatiladi), FAQAT
  ADMIN/SUPERVISOR uchun, FAQAT SO'ROV BO'YICHA (on-demand), avtomatik
  yuborilmaydi.
- `handlers/brigadier/stats.py` — brigadirga o'z brigadasi statistikasi
  (11.1-band, `get_brigade_monthly_stats`), on-demand.
- **Web panel** (`web/`) — chinakam SKELETON: `server.js` faqat static-file
  serve qiladi, `TODO: routes/ ichidagi routerlarni shu yerga ulash` degan
  izohdan boshqa hech narsa yo'q. Dashboard/grafik ko'rinish UMUMAN YO'Q.
- **Mijoz xabarnomalari** (12-band) — UMUMAN YO'Q. `clients`/`leads` jadvali
  yo'q, mijozga bog'lanadigan hech qanday ustun (`tasks`da ham) yo'q.
- **Oylik avtomatik reyting** (10.2-band) — UMUMAN YO'Q, hech qanday
  scheduled job yo'q.

## A. Web panel — statistika/dashboard (4-band, 10.2-band)

TZ 4-band: "Admin panelga kirish faqat ikki asosiy ish uchun zarur bo'lib
qolishi kerak: statistika ko'rish va xodim qo'shish." TZ 10.2-band: "Ikki
ko'rinish: DASHBOARD (grafik/diagramma) + JADVAL... Oxirida rahbarga umumiy
dashboard ko'rinishi kerak."

Bu — `web/`ning birinchi haqiqiy funksionalligi (hozir bo'sh skeleton).
CLAUDE.md qoidasi: "web/ o'qish/yozish qiladi, lekin bazani hech qachon
o'zgartirmaydi (migratsiya faqat bot/ orqali)".

### Kerakli ish (yangi, hech narsa yo'q)
- `web/src/config/db.js` — mavjud (Postgres ulanish konfiguratsiyasi,
  tekshirish kerak: `bot/.env`dagi bir xil `DATABASE_URL`dan foydalanadimi).
- `web/src/routes/stats.js` (yangi) — Express router, `bot/services/
  stats_service.py`dagi so'rovlarga MOS (lekin Node/JS'da qayta yoziladi —
  `web/` Python kodini import qila olmaydi, faqat SQL/ORM darajasida bir xil
  mantiq takrorlanadi: joriy oy/brigada/xodim kesimlari).
- `web/src/public/js/app.js` — "bitta oyna" printsipi (4.1-band): hammasi
  bitta sahifada, bo'limlar MODAL oynada ochiladi, chuqur navigatsiya yo'q.
  Grafik kutubxona tanlash kerak (Chart.js yoki shunga o'xshash — TZda aniq
  ko'rsatilmagan, ochiq texnik tanlov).
- Autentifikatsiya/avtorizatsiya — hozir `web/`da UMUMAN yo'q (login/sessiya
  yo'q). Admin panelga kirish qanday himoyalanishi (login+parol? Telegram
  orqali bog'lash?) — **TZda aniq ko'rsatilmagan, ochiq savol**.

**Tavsiya**: bu qismni boshlashdan oldin AskUserQuestion orqali aniqlashtirish:
(1) web panel autentifikatsiya usuli, (2) grafik kutubxona tanlovi (yoki
oddiy jadval bilan boshlab, grafikni keyinroq qo'shish).

## B. Telegram orqali davriy hisobotlar (10.2-band)

TZ matni: "Telegram orqali kunlik/haftalik/oylik qisqa hisobot + kerak
bo'lsa to'liq jadval." Hozir `/stats` FAQAT on-demand (foydalanuvchi o'zi
so'raganda). Yangi: SCHEDULED yuborish.

### Kerakli o'zgarishlar
- Yangi `jobs/report_job.py` — uchta funksiya yoki uchta cron job:
  - Kunlik (masalan har kuni 20:00, sozlanadigan): shu kunda tugagan/
    kechikkan tasklar qisqa xulosasi, ADMIN/SUPERVISOR'larga.
  - Haftalik (masalan yakshanba kuni): `get_employee_weekly_stats()` asosida,
    har xodimga yoki umumiy jadval.
  - Oylik (oy oxirida): to'liq `get_monthly_stats()` xulosasi.
- Vaqtlar `app_settings`ga qo'shilishi kerakmi yoki konstanta sifatida
  qolishi kerakmi — 16-band ("hammasi admin paneldan o'zgartiriladi")ga
  ko'ra SOZLANADIGAN bo'lishi kerak, lekin bu ustunlar hali yo'q (ochiq
  texnik qaror, band A/B doirasida hal qilinadi).
- `main.py`: yangi cron job(lar)ni ro'yxatga olish.

## C. Oylik eng yomon/eng yaxshi xodimlar reytingi (10.2-band)

TZ matni: "Oy oxirida tizim ENG YOMON ishlagan xodimlar reytingini
avtomatik chiqarib beradi (eng ko'p minus ball). Bu ro'yxat screenshot
qilinib jamoa guruhiga tashlanadi (ogohlantirish/oshkoralik vositasi).
Xuddi shunday ENG YAXSHI xodimlar ro'yxati ham chiqadi."

TZ 19-band ochiq savol #12: "Oylik 'eng yomon xodimlar' ro'yxatini guruhga
tashlash AVTOMATIKMI (bot o'zi yuboradi) yoki rahbar qo'lda screenshot
qiladimi?" — **BLOKLANGAN, tasdiq kerak**.

Agar avtomatik deb tasdiqlansa:
- `jobs/report_job.py` (yoki alohida `monthly_ranking_job.py`) — oy oxirida
  (masalan 1-sanada 00:05, oldingi oy uchun) `get_monthly_stats()`ni chaqirib,
  eng ko'p minus ball (yomon) va eng ko'p plus ball (yaxshi) top-N xodimni
  formatlab, sozlanadigan Telegram GURUH chatiga (`chat_id` — `app_settings`ga
  yoki alohida konfiguratsiyaga qo'shiladi) yuboradi.
- Guruh chat_id qayerdan olinadi — bot shu guruhga admin sifatida qo'shilgan
  bo'lishi kerak, `config.py`da yangi sozlama (`REPORT_GROUP_CHAT_ID`) yoki
  `app_settings`da yangi ustun.

Agar qo'lda (rahbar screenshot qiladi) deb tasdiqlansa — faqat `/stats`
buyrug'iga "eng yomon/eng yaxshi top-N" bo'limini qo'shish kifoya, alohida
scheduled job kerak emas.

## D. Mijozlarga avtomatik xabarnoma (12-band)

TZ matni: "Mahsulot qaysidir bo'limdan CHIQQANDA mijozga Telegram-bot orqali
avtomatik xabar/SMS boradi: 'Buyurtmangiz X bosqichdan o'tdi'. 'Stop'
bosilganda ham mijozga avtomatik xabarnoma yuboriladi."

Bu — tizimda HALI UMUMAN yo'q yangi subdomain: mijoz identifikatorini
saqlash kerak. Hozir `tasks` jadvalida mijozga ishora qiluvchi HECH QANDAY
ustun yo'q (`title`/`description` erkin matn, strukturalangan mijoz
ma'lumoti emas).

### Kerakli o'zgarishlar (yangi)
- Yangi `clients` jadvali (minimal): `full_name`, `phone_number` yoki
  `telegram_id` (mijoz botga ulanganmi yoki faqat SMS orqalimi — ochiq
  savol, TZ 19-band #11: "Mijoz xabarnomalari uchun asosiy kanal qaysi:
  Telegram bot, SMS, yoki ikkalasi? SMS provayderi tanlovi." —
  **BLOKLANGAN**).
- `tasks.client_id` (FK -> clients.id, nullable — MISC vazifalarda mijoz
  bo'lmasligi mumkin).
- `services/task_service.py`: `create_task()` mijoz tanlash/yaratish
  qadamini qo'shadi (admin/nazoratchi task yaratishda).
- `services/notification_service.py`: `notify_client_stage_advanced(bot,
  task_id)` (bosqich o'tganda), `notify_client_task_stopped(bot, task_id)`
  ("Stop" bosilganda) — yangi funksiyalar, `task_service.advance_task_stage()`
  va `timer_service.stop_task()`ga ulanadi.
- Agar SMS kanal ham tanlansa — yangi `services/sms_service.py`, tashqi
  SMS-shlyuz integratsiyasi (TZ: "~35 000 so'm/oy limit", provayder hali
  tanlanmagan — ochiq savol #11 ning davomi).

**Bu band butun tizimga yangi subdomain qo'shadi (mijozlar) — 5-bosqichdagi
Sotuv CRM moduli bilan potentsial ULANISH nuqtasi bor** (`clients` jadvali
ikkala bosqichda ham kerak bo'lishi mumkin — 5-bosqich boshlanishidan oldin
shu ustun/jadval strukturasini ikkala talabga mos qilib loyihalash tavsiya
etiladi, ikki marta migratsiya qilmaslik uchun).

## Ochiq savollar (bu bosqichni boshlashdan oldin hal qilinishi tavsiya etiladi)

1. Web panel autentifikatsiya usuli (A-qism).
2. Grafik kutubxona tanlovi yoki oddiy jadval bilan boshlash (A-qism).
3. Oylik reyting avtomatik yuborish yoki qo'lda (C-qism, TZ 19-band #12).
4. Mijoz xabarnoma kanali: Telegram/SMS/ikkalasi, SMS provayderi (D-qism,
   TZ 19-band #11).

## Tekshirish rejasi

- **A** (web dashboard): brauzerda ochib, real ma'lumot bilan statistika
  to'g'ri ko'rsatilganini tekshirish (CLAUDE.md talabi: "UI o'zgarishlari
  uchun avval brauzerda sinab ko'rish").
- **B/C** (scheduled hisobotlar/reyting): sun'iy ravishda job vaqtini
  o'zgartirib yoki qo'lda `run()` chaqirib, real Telegram guruh/xodimlarga
  xabar yetib borishini tekshirish.
- **D** (mijoz xabarnoma): sun'iy mijoz+task yaratib, bosqich o'tkazib,
  mijozga (test Telegram akkaunt) xabar kelishini tekshirish.
- Har doim real Railway DB'ga qarshi, `bot/_smoke_phase4_*.py` orqali.
