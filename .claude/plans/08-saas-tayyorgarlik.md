# SaaS tayyorgarlik: billing (Ping), multi-tenant, video darslar (TZ 6-bosqich, B/C/D-qism)

Holat: BLOKLANGAN — TZ 19-band ochiq savol #13 (Ping shartnoma/narxlash)
hali tasdiqlanmagan. Quyidagi dizayn **spekulyativ** — real implementatsiya
emas, faqat texnik reja (foydalanuvchi bilan 2026-07-17'da tasdiqlangan
qaror: "taxminiy texnik dizayn yozing", kod yozilmasin).

TZ manbasi: 15-band to'liq (SaaS mahsulot, "AmoCRM qotili"), 16-band
(multi-tenant tayyorlik), 14-band (billing/hosting qatorlari).

TZning o'zi buni **2-FAZA** deb ataydi: *"amalga oshirilishi 2-fazada."*
Demak, hozirgi 6 bosqichlik rejaning tashqarisida — bu hujjat faqat
kelajakda ish boshlanganda boshlang'ich nuqta bo'lish uchun saqlanadi.

## B. Billing (Ping) integratsiyasi (14.1/15.2-band)

TZ matni: *"To'lov faqat billing (Ping) integratsiyasi orqali... OBUNA
modeli: mijoz to'lamasa tizim AVTOMATIK O'CHADI."*

**BLOKLANGAN**: Ping'ning haqiqiy API hujjatlari kelmaguncha (webhook
payload shakli, autentifikatsiya usuli, event nomlari) quyidagi dizayn
deyarli aniq o'zgaradi.

### Taxminiy ma'lumot modeli

```
subscriptions
  id, organization_id (FK -> organizations, C-qismga qarang), status
  (active/past_due/suspended), ping_customer_id, current_period_end,
  plan, created_at, updated_at

billing_events (Ping webhook log — audit uchun)
  id, subscription_id, ping_event_id (UNIQUE — takroriy webhook himoyasi),
  event_type, raw_payload (JSON), processed_at
```

`financial_suggestions`ga o'xshab (8.6-band naqshi): hech qanday haqiqiy
pul o'tkazmasi kodda amalga oshirilmaydi — Ping tashqi tizim, bot faqat
uning webhook orqali yuborgan holat o'zgarishlarini yozib boradi.

### Taxminiy oqim

1. Yangi SaaS mijoz ro'yxatdan o'tganda → Ping'da customer/subscription
   yaratiladi (aniq API chaqiruv Ping hujjati kelmaguncha noma'lum).
2. Ping to'lov holatini **webhook** orqali yuboradi (`web/`da yangi
   `/api/webhooks/ping` route — imzo tekshiruvi Ping'ning HMAC sxemasiga
   bog'liq, hozircha noma'lum).
3. Webhook handler `billing_events`ga yozadi (idempotent — `ping_event_id`
   UNIQUE orqali), so'ng `subscriptions.status`ni yangilaydi.
4. `status != active` bo'lsa: yangi middleware (`middlewares/
   subscription_gate.py`) tegishli `organization_id`ga tegishli barcha bot
   so'rovlarini bloklaydi — "tizim AVTOMATIK O'CHADI" talabi shu orqali.

### Ochiq savollar (Ping shartnoma kelgach)

- Webhook autentifikatsiya usuli (HMAC, IP allowlist?).
- Grace period bormi yoki `past_due` darhol `suspended`ga aylanadimi?
- Bitta obuna butun tashkilotni yopadimi yoki qisman cheklash bormi?

## C. Obuna va multi-tenant tayyorlik (15.1/15.2/16-band)

**2-FAZA ISHI, HOZIR QURILMAYDI.** Deyarli har bir jadvalga
`organization_id` FK qo'shish va HAR BIR repository so'rovini shu bilan
filtrlash kerak — bitta xato joy = boshqa tashkilotning ma'lumotini
ko'rsatish (jiddiy xavfsizlik nuqsoni). TZning o'zi buni ataylab keyingi
fazaga qoldirgan.

### Taxminiy migratsiya tartibi (2-faza boshlanganda qayta ko'rib chiqiladi)

1. `organizations` jadvali (`id`, `name`, `created_at`).
2. Nullable `organization_id` FK top-level jadvallarga (`departments`,
   `employees`, `clients`) — bitta martalik data-migration bilan mavjud
   qatorlar "Melores Mebel"ga bog'lanadi, keyin NOT NULL qilinadi.
3. Bog'liq jadvallar (`tasks`, `leads`) `organization_id`ni ota jadvali
   orqali oladi (takrorlanmasin).
4. Har bir repository metodiga `organization_id` parametri; har chaqiruv
   joriy foydalanuvchining tashkiloti bilan (middleware orqali).
5. Bu qadam TO'LIQ tugagunga qadar yangi SaaS mijoz qo'shib bo'lmaydi —
   hozircha faqat bitta tashkilot (Melores Mebel) bor, shoshilinch yo'q.

### Ochiq savollar

- Trello: har tashkilot o'z akkountiga egami yoki bitta umumiy akkountda
  ko'p board? TZda ko'rsatilmagan.

## D. Video darslar bo'limi (15.2-band)

**2-FAZA ISHI.** Ichki Melores Mebel jamoasi uchun EMAS — kelajakdagi SaaS
mijozlar uchun o'quv materiali.

| Variant | Ishlash tartibi | Cheklov |
|---|---|---|
| Telegram himoyalangan kanal | "Forward taqiqlangan" (`protect_content`) yopiq kanal | aiogram allaqachon loyihada bor — yangi bog'lanish shart emas |
| Web streaming | `web/`ga video player, yuklab olinmaydigan (signed URL) | yangi infratuzilma (video storage/CDN) kerak |

**Tavsiya** (2-faza boshlanganda qayta tasdiqlanadi): Telegram varianti —
mavjud infratuzilmani ishlatadi, yangi storage/CDN qo'shmaydi.

### Ochiq savol

Kanalga kirish obuna holatiga (B-qism) bog'lanadimi (obuna to'xtasa
kanaldan chiqariladimi)?

## Tekshirish rejasi

2-faza rejalashtirilganda, Ping shartnomasi tasdiqlangach, alohida
aniqlanadi — bu hujjatdagi dizayn boshlang'ich nuqta, yakuniy reja emas.

## Tugagach

Faqat Ping shartnoma/narxlash (#13) tasdiqlangach va 2-faza rasman
boshlangach — shu paytda bu hujjat to'liq qayta yoziladi (aniq API
shakllari bilan), keyin amalga oshirilib, `.claude/plans/`dan olib
tashlanadi.
