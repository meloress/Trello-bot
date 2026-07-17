# 3-bosqich: KPI — minus/plus ball, brigadir ulushi, checklist jarayoni

Holat: BAJARILGAN, real Railway Postgres'da sinovdan o'tgan. TZda "2-etap,
3-bosqich" sifatida rasman belgilangan: "KPI: minus/plus ball, brigadir
ulushi, checklist jarayoni (qoidalar hujjati asosida)".

TZ manbasi: 8-band to'liq (8.1–8.7), ayniqsa 8.4 (brigadir ulushi va plus
ball), 8.5 (maosh/avans kuniga ta'sir), 8.6 (moliyaviy javobgarlik
bayroqlash), 8.7 (xodim roziligi).

**Sinov holati**: `alembic upgrade head` real Railway DB'ga muvaffaqiyatli
qo'llandi (`f98817708ac9`). `bot/_smoke_phase3_kpi.py` orqali real DB'ga
qarshi to'liq oqim tekshirildi (Trello'siz, MISC vazifalar bilan): plus ball
(30 soat oldin -> +1), grace period (10 soat kech -> 0), minus jarima (50
soat kech -> shifted bracket -2), 8.6 avtomatik bayroqlash (6 kunlik bosqich
-> applicable, idempotentlik tasdiqlandi) — barchasi kutilganidek ishladi,
test qatorlari o'chirildi, skript o'zi ham ishlatilgach o'chirildi.

## A. Plus ball mezonlari (8.4-band) — BAJARILGAN

Yondashuv (foydalanuvchi tasdiqlagan, 2026-07-17): faqat muddatdan oldin
tugatish mezon, sifat/nazoratchi tasdig'i talab qilinmaydi. Aniq formula
(foydalanuvchi tasdiqlagan, 2026-07-17): `dayIndex = hours_early // 24`,
har TO'LIQ kun uchun `plus_ball_per_day` ball (default 1), `plus_ball_max_days`
kunidan (default 2) ortig'iga qo'shilmaydi (cap). Ikkalasi ham
`app_settings` orqali sozlanadigan (16-band, kodga tikilmagan).

- `penalty_service.calculate_plus_ball(hours_early)` — endi async, real
  formula (avvalgi stub emas).
- `penalty_service.apply_plus_ball_for_employees()` — yangi funksiya,
  `calculate_and_apply_task_penalty()` muddatdan OLDIN tugagan vazifa uchun
  chaqiradi. Brigadir ulushi (8.4-band) va 8.5-band to'lov kuni qayta
  hisoblash ikkalasi ham avtomatik ishlaydi (minus yo'li bilan bir xil umumiy
  yadro, `_write_scores_for_employees()`).
- `notify_penalty_applied()` o'zgarishsiz — musbat/manfiy ballarni allaqachon
  farqlaydi.

## B. Brigadir ulushi aniq foizi (8.4-band) — BAJARILGAN

0.33 (1/3) YAKUNIY qiymat sifatida tasdiqlangan (2026-07-17). Kod o'zgarishi
kerak emas edi — default qiymat allaqachon to'g'ri. Qo'shimcha: ulush endi
ANIQ ikki yo'nalishda ham ishlaydi (musbat/manfiy), `_apply_brigade_share_for_worker`
sof arifmetika bo'lgani uchun bu allaqachon avtomatik ta'minlangan edi.

## Yon-effekt: 24 soatlik "grace period" (8.1/8.2-band)

Plus ball formulasi bilan bir vaqtda foydalanuvchi minus jarima uchun ham
aniq dayIndex-asosli formulani tasdiqladi: `hours_late < 24` bo'lsa hech
qanday jarima yo'q (avvalgi versiyada 0 soatdan boshlab -1 berilardi).
`penalty_rules` jadvalidagi 4 ta bracket +24 soatga siljitildi (score'lar
o'zgarmadi): endi `[24,48)→-1, [48,72)→-2, [72,96)→-5, [96,120)→-8`,
120+ hali kelishilmagan (`PenaltyRuleNotConfiguredError`). Migratsiya:
`f98817708ac9` (`UPDATE penalty_rules SET min/max_hours_late += 24`).

## C. Checklist jarayoni (6.2-band) — o'zgarishsiz

2-bosqichda hal qilingan (avtomatik, bo'lim zanjiri bo'yicha). 3-bosqichda
qolgan yagona narsa — statistikada checklist holatini ko'rsatish — hali
ham 4-bosqichga (dashboard) bog'liq, bu yerda qilinmadi.

## D. 8.6-band: moliyaviy javobgarlik bayroqlash — ASOSIY QISM BAJARILGAN

Foydalanuvchi tasdiqlagan (2026-07-17): faqat bayroqlash emas, summa
hisob-kitobi ham kerak — ikkita mustaqil pure-function bilan:

- `financial_service.calculate_wage_deduction_suggestion()` — 1-qoida
  (bo'lim aybi bilan mijozdan to'lov olinmasa): `stage_duration_days >
  threshold_days` bo'lsa applicable; summa ma'lum bo'lsa `* 0.5` taklif.
- `financial_service.calculate_advance_waiver()` — 2-qoida (80% avans +
  kechikish): applicable bo'lsa `order_total_value * (waiver_percent/100)`
  kechiriladigan summa.
- Natijalar yangi `financial_suggestions` jadvaliga yoziladi, `status` doim
  `pending_manager_review` — tasdiqlash/rad etish BOSHQA (hali qurilmagan)
  modul ishi, bu yerda faqat interfeys tayyor.

**Avtomatik ishlaydigan qism**: `overdue_watch_job._process_financial_flags()`
har soat bosqich davomiyligini (`task.started_at`) tekshiradi, chegaradan
(`financial_flag_threshold_days`, default 5) ortiq bo'lsa 1-qoida bo'yicha
taklif yaratadi (summasi hali `NULL` — "kutilmoqda"), NAZORATCHI+ADMIN'larga
signal yuboradi (`notify_financial_flag`).

**HALI qurilmagan (bu bosqich doirasidan tashqarida qoldirilgan, ataylab)**:
tizimda hech qanday to'lov/avans/shartnoma summasi manbai yo'q (moliya
moduli TZ 18-band bo'yicha chegaradan tashqarida), shuning uchun:
- `amount_withheld_by_customer` (1-qoida summasi) va 2-qoidaning barcha
  kirish qiymatlari (`advance_percent_paid`, `order_total_value`, `is_late`)
  HAR DOIM qo'lda kiritiladi — buning uchun admin Telegram UI/FSM oqimi hali
  YO'Q (`financial_service.create_advance_waiver_suggestion()` chaqirishga
  tayyor, lekin hech qayerdan chaqirilmaydi).
- Bu UI 4-bosqich (statistika/dashboard) bilan tabiiy bog'liq — o'sha
  bosqichda qurilishi rejalashtirilgan, bu yerda qasddan qoldirilgan (scope
  creep emas).

## E. 8.7-band: xodimning roziligi — o'zgarishsiz

Process/siyosat xarakterli, kod talab qilinmaydi ("Stop" tugmasi allaqachon
ishlaydi).

## Yangi migratsiya: `f98817708ac9`

- `app_settings`ga 5 ta yangi ustun: `plus_ball_per_day`, `plus_ball_max_days`,
  `financial_flag_threshold_days`, `advance_threshold_percent`,
  `advance_waiver_percent` (barchasi `/settings` orqali tahrirlanadi).
- `penalty_rules` bracket'lari +24 soatga siljitilgan (data migration).
- Yangi `financial_suggestions` jadvali.

## Tekshirilgan

Ikki bosqichda: avval sof funksiyalar/formulalar (`py_compile` + qo'lda
assert, DB'siz) foydalanuvchi bergan test jadvallariga solishtirildi;
keyin `.env` mavjud bo'lgach real Railway DB'ga qarshi (`alembic upgrade
head` + `bot/_smoke_phase3_kpi.py`, Trello'siz MISC vazifalar bilan)
to'liq oqim — plus ball, grace period, shifted minus bracket, 8.6 avtomatik
bayroqlash + idempotentlik. Barchasi kutilgan natijani berdi.

## QILINMAGAN

- Real Telegram botda `/settings` orqali yangi 5 ta maydonni qo'lda UI
  sinovi (kod real DB'ga qarshi tekshirildi, lekin Telegram interfeysi
  orqali emas).
- Real "Test" Trello board bilan integratsiya sinovi (kerak emas edi — bu
  bosqichning barcha o'zgarishlari Trello'ga umuman tegmaydi, faqat DB).
- 8.6-band advance-waiver uchun admin qo'lda-kiritish UI (qasddan
  4-bosqichga qoldirilgan, yuqoridagi D bo'limiga qarang).
