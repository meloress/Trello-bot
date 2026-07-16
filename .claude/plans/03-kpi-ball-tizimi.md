# 3-bosqich: KPI — minus/plus ball, brigadir ulushi, checklist jarayoni

Holat: NAVBATDA (2-bosqich tugagach boshlanadi). TZda "2-etap, 3-bosqich"
sifatida rasman belgilangan: "KPI: minus/plus ball, brigadir ulushi,
checklist jarayoni (qoidalar hujjati asosida)".

TZ manbasi: 8-band to'liq (8.1–8.7), ayniqsa 8.4 (brigadir ulushi va plus
ball), 8.5 (maosh/avans kuniga ta'sir), 8.6 (moliyaviy javobgarlik
bayroqlash), 8.7 (xodim roziligi).

## MUHIM: bu bosqichning yadrosi ALLAQACHON ishlayapti

Boshqa bosqichlardan farqli o'laroq, 8-bandning katta qismi 1-bosqich
davomida `services/penalty_service.py`da qurib bo'lingan. Bu hujjat asosan
QOLGAN, hali qilinmagan yoki ochiq savolga bog'liq bo'laklarni sanaydi —
mavjud narsani qayta yozish EMAS.

### Allaqachon ishlaydigan qismlar (`penalty_service.py`, tekshirilgan)
- **8.1/8.2 (kechikish jarima jadvali)**: `calculate_and_apply_task_penalty()`
  — vazifa yakunlanganda chaqiriladi, `finished_at > deadline` bo'lsagina
  ishga tushadi, `penalty_rules` jadvalidan (`department_id`ga qarab yoki
  global fallback) mos qoidani topib ISHCHI (`Role.WORKER`) xodim(lar)ga
  `KpiLog` yozadi. Muddatida/oldin tugagan bo'lsa — hech narsa yozilmaydi.
  Qoida topilmasa `PenaltyRuleNotConfiguredError` (eng yaqin qiymatga
  "yopishib qolmaydi" — atayin qat'iy).
  Seed qilingan bracket'lar (`835647e37c2a` migratsiyasi, global):
  0-24 soat -> -1, 24-48 soat -> -2, 48-72 soat -> -5, 72-96 soat -> -8.
  96 soatdan keyingisi hali kelishilmagan.
- **8.4 (brigadir ulushi)**: `_apply_brigade_share_for_worker()` — ishchi
  ball olganda (bonus/jarima), uning brigadiriga `app_settings.
  brigade_share_ratio` (default 0.33) nisbatida avtomatik ulush yoziladi
  (`apply_brigade_share()`). Brigada/brigadir yo'q bo'lsa jim o'tkaziladi.
  Sozlanadigan (`/settings` orqali, kodga tikilmagan).
- **8.5 (maosh/avans kuniga ta'sir)**: `update_payment_date_if_needed()` —
  joriy oyda to'plangan minus ballarga qarab (`balls_per_day_shift`,
  default 5) `employee.next_payment_date`ni `BASE_PAYMENT_DAY` (15,
  hozircha konstanta) dan siljitadi. Har chaqirilganda NOLDAN qayta
  hisoblanadi (idempotent) — alohida "oylik reset" job kerak emas.
- **Qo'lda ball**: `add_manual_kpi(employee_id, score, reason)` — admin/
  nazoratchi tomonidan qo'lda bonus/jarima yozish, `reason` majburiy.
- **Bildirishnoma**: `notification_service.notify_penalty_applied()` —
  ball yozilganda xodimga sabab+miqdor bilan xabar.

### QILINMAGAN / TO'LIQ EMAS qismlar

## A. Plus ball mezonlari (8.4-band, TZ 19-band ochiq savol #4)

TZ matni: "Plus ball mezonlari (muddatidan oldin/sifatli bajarilgan ish
uchun) ham alohida tasdiqlanishi kerak." Hozir `penalty_service.
calculate_plus_ball(task_id) -> int` STUB — doim `0` qaytaradi, tanaffussiz
kod izohida "mezon kelishilgach to'ldiriladi" deb yozilgan.

**HAL QILINDI** (foydalanuvchi tasdiqlagan, 2026-07-17): faqat muddatdan
oldin tugatish mezon bo'ladi — sifat/nazoratchi tasdig'i talab qilinmaydi
(eng oddiy variant tanlandi). Aniq formula (necha soat oldin -> necha ball)
hali kod yozishdan oldin belgilanishi kerak — bu 3-bosqich boshlanganda
hal qilinadi, hozircha faqat "yondashuv" tasdiqlangan, "formula" emas.

Mezon aniqlangач:
- `penalty_service.calculate_plus_ball()` to'ldiriladi va `finish_task()`
  yoki `advance_task_stage()` oqimiga ulanadi (qaysi payt chaqirilishi —
  vazifa tugaganda yoki bosqich tugaganda — mezonga bog'liq).
- `notify_penalty_applied()` allaqachon musbat/manfiy ballarni farqlaydi
  (`score > 0` -> "🎁 bonus"), qo'shimcha o'zgarish shart emas.

## B. Brigadir ulushi aniq foizi (8.4-band, TZ 19-band ochiq savol #3)

TZ matni: "Ishchining minus balidan brigadirga ulush o'tishi
rejalashtirilgan (ilgari taklif: ≈1/3). Aniq foiz hali RASMAN
tasdiqlanmagan." Hozir `app_settings.brigade_share_ratio` default `0.33`
bilan **KODDA ALLAQACHON SOZLANADIGAN** (admin `/settings` orqali
o'zgartira oladi).

**HAL QILINDI** (foydalanuvchi tasdiqlagan, 2026-07-17): 0.33 (1/3) YAKUNIY
qiymat sifatida tasdiqlandi. Kod o'zgarishi kerak emas — default qiymat
allaqachon to'g'ri.

## C. Checklist jarayoni (6.2-band, 2-bosqich C.2 bilan bog'liq)

TZ 19-band ochiq savol #1: "Checklist qanday to'ldiriladi — tayyor tugmali
variantlar orqalimi yoki erkin matn bilanmi?" — bu savol **2-bosqichda**
foydalanuvchi bilan hal qilingan: bo'lim zanjiri bo'yicha avtomatik (har
bosqich = 1 punkt, avtomatik belgilanadi, xodim qo'lda checklist matni
yozmaydi). Demak, checklist jarayonining ASOSIY qismi 2-bosqichning C.2
qismida amalga oshiriladi, 3-bosqichda faqat quyidagilar qoladi:

- Checklist holatini statistika/hisobotda ko'rsatish (qaysi bosqichlar
  bajarilgan, qaysilari qolgan — `stats_service`ga integratsiya, ixtiyoriy,
  agar foydalanuvchi so'rasa).
- Agar kelajakda "erkin qo'shimcha checklist punktlari" (masalan sifat
  nazorati qadamlari) kerak bo'lsa — bu YANGI ochiq savol, hozircha TZda
  yo'q, o'ylab topilmaydi.

## D. 8.6-band: moliyaviy javobgarlik bayroqlash

TZ matni: "Agar biror bo'lim aybi bilan mijozdan to'liq to'lov olinmasa va
o'sha bo'lim shu bosqichda 4-6 kundan ortiq vaqt o'tkazgan bo'lsa..." va
"2025-yil 1-fevraldan: 80% avans olingandan keyin muddat o'tkazib
yuborilsa, qolgan 20% mijozdan talab QILINMAYDI." TZ o'zi aniq cheklaydi:
"Tizim, hozircha, faqat quyidagilarni bayroqlashi kifoya: 'bu bosqich 4
kundan ortiq davom etdi' va '80% avans olingan-olinmagani'. Aniq summa
hisob-kitobi va to'lovni amalga oshirish keyingi (moliya) fazaga
qoldiriladi" (18-band: moliya moduli bu TZ chegarasidan tashqarida).

TZ 19-band ochiq savol #4b: "Tizim faqat BAYROQLASHI yetarlimi, yoki summa
hisob-kitobi ham kerakmi?" — **QISMAN HAL QILINDI** (foydalanuvchi
tasdiqlagan, 2026-07-17): faqat bayroqlash EMAS, summa hisob-kitobi ham
kerak. **Hali BLOKLANGAN qoladi**: bu tizimda hech qanday to'lov/avans/
shartnoma summasi ma'lumoti umuman yo'q (moliya moduli yo'q, TZ 18-band
buni tashqarida deb belgilaydi) — "summa hisob-kitobi" qilish uchun avval
qaysi summalar (buyurtma narxi? avans foizi? valyuta?) va ular qayerdan
kiritilishi (admin qo'lda? alohida moliya integratsiyasi?) ANIQLANISHI
SHART. 3-bosqich boshlanganda shu tafsilotlar bo'yicha qo'shimcha savol
kerak bo'ladi — taxmin qilinmaydi.

Agar faqat bayroqlash tasdiqlansa (TZning o'z matni shuni aytadi):
- `tasks` jadvaliga yangi bool/flag ustun: masalan `flagged_long_duration`
  (bosqich 4-6 kundan ortiq davom etganda, `overdue_watch_job` yoki alohida
  kunlik job orqali avtomatik belgilanadi).
- `advance_prepayment_percent` kabi ustun — 80%/20% avans holatini kim
  kiritadi? TZda aniq emas — bu ham ochiq savol, chunki hozirgi tizimda
  to'lov/avans ma'lumoti umuman yo'q (moliya moduli yo'q). Ehtimol admin
  vazifa yaratishda qo'lda belgilaydi (checkbox: "80% avans olingan").
- Bayroqlangan tasklar admin/rahbar statistikasida alohida ko'rinadi
  (4-bosqichdagi statistika bilan bog'liq).

**Bu band boshqalardan ko'ra ko'proq ochiq savol** — amalga oshirishdan
oldin AskUserQuestion orqali aniqlashtirish tavsiya etiladi.

## E. 8.7-band: xodimning roziligi

TZ matni: "Har bir xodim ushbu jarima qoidalariga rozi bo'lishi kerak; rozi
bo'lmasa, ishlamaslik huquqiga ega. Norozilik yoki qarshilikni bildirishning
yagona rasmiy yo'li — 'Stop' tugmasi." Bu band **process/siyosat** xarakterli
— "Stop" funksiyasi allaqachon 2-bosqichda (aslida 1-bosqichda) to'liq
ishlaydi. Qo'shimcha kod talab qilinmaydi, faqat hujjatlashtirish (masalan
xodim ro'yxatga olinganda "jarima qoidalariga rozilik" matnini ko'rsatish —
agar foydalanuvchi shuni xohlasa, aks holda process darajasida qoladi).

## Migratsiya (agar D bo'yicha tasdiq kelsa)

Yangi ustunlar faqat 8.6-band D qismi tasdiqlansa kerak bo'ladi (`tasks`
jadvaliga). Boshqa hech narsa (A/B/C/E) yangi migratsiya talab qilmaydi —
mavjud infratuzilma (`penalty_rules`, `app_settings.brigade_share_ratio`)
allaqachon yetarli.

## Tekshirish rejasi

- **A** (plus ball): mezon tasdiqlangach, sun'iy "muddatidan oldin tugagan"
  task yaratib `calculate_plus_ball()`/yangi hisoblash to'g'ri musbat ball
  qaytarishini va `KpiLog`ga yozilishini tekshirish.
- **B** (brigadir ulushi): faqat qiymat yangilash, kod o'zgarishi yo'q —
  alohida smoke-test shart emas, mavjud `_apply_brigade_share_for_worker`
  logikasi 1-bosqichda allaqachon sinovdan o'tgan.
- **D** (8.6 bayroqlash, tasdiqlangandan keyin): sun'iy 5 kunlik bosqichda
  turgan task -> flag avtomatik qo'yilganini tekshirish.
- Har doim real Railway DB'ga qarshi, `bot/_smoke_phase3_*.py` orqali,
  ishlatilgach o'chiriladi.
