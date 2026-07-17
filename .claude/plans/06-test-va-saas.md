# 6-bosqich: Umumiy test, ishga tushirish, SaaS tayyorgarlik

Holat: **A-QISMI BAJARISHGA TAYYOR** (kod/skript/deploy-config yozilgan,
ishga tushirish operatorning qo'lida). **B/C/D-qismlari SPEKULYATIV DIZAYN**
— TZ 19-band #13 ochiq savoli (Ping shartnoma/narxlash) hali yopilmagani
uchun real implementatsiya emas, faqat texnik reja (pastga qarang).

TZ manbasi: 15-band to'liq (SaaS mahsulot, "AmoCRM qotili"), 16-band
(nofunksional talablar — ishonchlilik, multi-tenant tayyorlik), 14-band
(texnik arxitektura — billing/hosting qatorlari).

## Bu bosqich ikkita SIFAT JIHATDAN FARQLI qismdan iborat

1. **Umumiy test/ishga tushirish (A)** — 1-5-bosqichlarda qurilgan tizimni
   yaxlit tekshirish, production'ga chiqarish. Muhandislik ishi — hech qanday
   tashqi blokerga bog'liq emas, hozir bajarilishi mumkin.
2. **SaaS tayyorgarlik (B/C/D, 15-band)** — TZning o'zi buni **2-FAZA** deb
   ataydi: "amalga oshirilishi 2-fazada." TZ 19-band #13: Ping shartnoma va
   narxlash **hali tasdiqlanmagan** — shu sabab bu uch qism kodga
   aylantirilmaydi, faqat texnik dizayn hujjatlashtiriladi (foydalanuvchi
   bilan 2026-07-17'da tasdiqlangan qaror: "taxminiy texnik dizayn yozing").

---

## A. Umumiy test va ishga tushirish — BAJARISHGA TAYYOR

### A.0 Boshlash sharti (bajarildi)

- Phase 1-5 kodi **commit qilingan** (2026-07-17, "Phases 3-5: KPI
  plus-ball/financial flags, stats dashboard/client notifications, sales
  CRM"). Railway DB migration head: `11e2c2cee985`, `python main.py`
  toza import bo'lishi tekshirildi.

### A.1 Uchdan-uchga (E2E) smoke test — skript tayyor

`bot/_smoke_e2e_full.py` yozilgan (vaqtinchalik, CLAUDE.md konvensiyasi
bo'yicha ishlatilgach o'chiriladi). Bitta ketma-ket oqimda tekshiradi:

1. Buyurtma yaratish (`task_service.create_task`, muddat ATAYLAB o'tgan —
   real vaqt kutish shart emas).
2. `overdue_watch_job.run()` — ACTIVE -> OVERDUE avtomatik aniqlash.
3. `task_service.reassign_task_brigade()` — 8.3-band avto-o'tkazish signali
   asosidagi qo'lda o'tkazish, eski brigadaga darhol jarima.
4. `timer_service.finish_task()` + `penalty_service.calculate_and_apply_task_penalty()`
   — kechikish jarimasi.
5. `task_service.advance_task_stage()` -> `activate_pending_stage()` —
   ko'p bosqichli progressiya (2-bosqichga o'tish).
6. 2-bosqichni muddatidan OLDIN yakunlash — plus ball yo'li.
7. `advance_task_stage()` ikkinchi marta — bo'lim zanjiri tugaganda `None`
   qaytishini tekshiradi.
8. `notification_service.notify_client_stage_advanced()` — mijoz
   xabarnomasi (client.telegram_id NULL bo'lsa ham xatosiz o'tishi kerak).
9. `stats_service.get_daily_stats()` / `get_monthly_stats()` — statistika.
10. `report_job.run_daily()` — davriy hisobot yuborish.
11. Tozalash: yaratilgan KPI/assignment/task/client qatorlari o'chiriladi
    (FK tartibiga rioya qilib — bola task ota task'dan oldin).

**Oldindan shart (Test board'da qo'lda tayyorlanishi kerak, skript o'zi
tekshiradi va aniq xabar bilan to'xtaydi agar yo'q bo'lsa):**
- Kamida ikkita `next_department_id` bilan zanjirlangan bo'lim, ikkalasida
  ham `trello_list_id` sozlangan.
- Har ikkala bo'limda kamida bitta faol brigada, xodimlari bilan.

**Ishga tushirish:**
```bash
cd bot && .venv\Scripts\python _smoke_e2e_full.py
```
Muvaffaqiyat belgisi: oxirida `Phase 6-A E2E smoke test OK`. Xato chiqsa —
qaysi qadamda to'xtaganini ko'rsatadi, shu servisga qarab tuzatiladi.

**MUHIM**: bu skript real Trello "Test" board'da karta yaratadi/ko'chiradi
va real Telegram xabarlari yuboradi (agar test xodimlar/mijoz haqiqiy
`telegram_id`ga ega bo'lsa). Ijro etilmagan — operator (yoki keyingi
sessiyada Claude, aniq ruxsat bilan) `Test` board tayyor bo'lgach ishga
tushiradi, keyin skriptni o'chiradi (`rm bot/_smoke_e2e_full.py`) va
`shared/db-schema.md`/bu faylni "sinovdan o'tdi" deb yangilaydi.

### A.2 Production infratuzilmaga o'tish — Railway (foydalanuvchi bilan tasdiqlangan)

Hosting tanlovi: **Railway**, xuddi Postgres joylashgan joyning o'zi — bot
alohida Railway xizmati (service) sifatida, bir xil loyihada (project).

`bot/railway.json` yozilgan:
```json
{
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "startCommand": "python main.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

16-bandning "xatolik holatida avtomatik qayta ishga tushirish" talabi shu
`restartPolicy` orqali yopiladi — alohida `systemd`/`pm2`/Docker
supervisor SHART EMAS (Railway buni platforma darajasida qiladi, ponytail
qoidasi: native platforma xususiyati > qo'shimcha vosita).

**Qo'lda bajariladigan qadamlar (Railway dashboard, kod bilan
avtomatlashtirilmaydi — bu deploy/infra harakati, repo tashqarisida):**

1. Railway loyihasida yangi xizmat qo'shish: "Deploy from GitHub repo",
   shu repo, **Root Directory = `bot`** (railway.json shu papkada
   o'qiladi).
2. Xizmat Environment Variables bo'limiga qo'shish (root `.env`dagi bilan
   bir xil qiymatlar): `BOT_TOKEN`, `TRELLO_API_KEY`, `TRELLO_TOKEN`,
   `DATABASE_URL` (agar Postgres xizmati bir xil loyihada bo'lsa, Railway
   `DATABASE_URL`ni avtomatik taklif qiladi — reference variable sifatida
   bog'lash mumkin, qo'lda ko'chirish shart emas).
3. Deploy qilish, loglarni kuzatish (`python main.py` xatosiz, `Update
   received` yozuvlar polling ishlayotganini bildiradi).
4. `web/` uchun ham xohlasa xuddi shunday alohida xizmat (Root
   Directory = `web`, start command `npm start`, `WEB_ADMIN_PASSWORD`/
   `WEB_SESSION_SECRET` environment variable sifatida) — TZda web panel
   24/7 bo'lishi majburiy emas, lekin bir xil platformada bo'lgani uchun
   qo'shish arzon.

### A.3 Production Trello board'larga o'tish

- A.1/A.2 tugagach, `departments.trello_list_id` va (agar sales ham launch
  qilinsa) `app_settings.sales_board_lists` qiymatlarini "Test" board list
  ID'laridan **haqiqiy production board'lar** ("Fasad seh", "Ezza sotuv",
  "Melores Mebel sotuv") list ID'lariga qo'lda UPDATE qilish (mavjud
  konvensiya — bot UI orqali emas, to'g'ridan-to'g'ri bazada, xuddi Test
  board sozlangani kabi).
- Bu bosqichda ORTIQ "sinov" emas — birinchi marta haqiqiy buyurtmalar
  bilan ishlaydi. Backup: o'tishdan oldin Railway Postgres'ning snapshot/
  backup funksiyasidan foydalanib bitta zaxira nuqtasi olish tavsiya
  etiladi (Railway buni dashboard'dan bir necha bosishda qiladi, alohida
  skript kerak emas).
- Rollback rejasi: agar birinchi kunlarda jiddiy xato chiqsa,
  `departments.trello_list_id`ni Test board'ga qaytarib, botni to'xtatish
  yetarli (DB va Trello alohida — birortasini "buzish" ehtimoli yo'q,
  faqat qaysi board bilan gaplashishini o'zgartiradi).

### A.4 Kuzatuv davri

Avtomatlashtirilgan test emas — operatsion nazorat: production'ga
chiqqandan keyin bir necha kun Railway loglarini kuzatish (xatolik
darajasi, `logger.exception` chaqiruvlari), kamida bitta to'liq kunlik
eslatma/hisobot sikli haqiqiy ishlashini tasdiqlash.

---

## B. Billing (Ping) integratsiyasi — SPEKULYATIV DIZAYN (14.1/15.2-band)

> **BLOKLANGAN**: TZ 19-band ochiq savol #13 — Ping shartnoma shartlari va
> narxlash hali tasdiqlanmagan. Quyidagi dizayn **taxminiy** — Ping'ning
> haqiqiy API hujjatlari kelganda deyarli aniq o'zgaradi (webhook payload
> shakli, autentifikatsiya usuli, event nomlari noma'lum). Kod yozilmaydi,
> faqat arxitektura shakli.

TZ matni: "To'lov faqat billing (Ping) integratsiyasi orqali — to'g'ridan-
to'g'ri karta ulanmaydi (soliq xavfi)." va "OBUNA (podpiska) modeli: mijoz
to'lamasa tizim AVTOMATIK O'CHADI."

### B.1 Taxminiy ma'lumot modeli

```
subscriptions
  id, organization_id (FK -> organizations, C-qismga qarang), status
  (active/past_due/suspended), ping_customer_id, current_period_end,
  plan (tarif nomi), created_at, updated_at

billing_events (Ping webhook log — audit uchun, tashqi tizim holatini
qayta qurish kerak bo'lganda)
  id, subscription_id, ping_event_id (UNIQUE — takroriy webhook himoyasi),
  event_type, raw_payload (JSON), processed_at
```

Boshqa `financial_suggestions`ga o'xshab (8.6-band naqshi): **hech qanday
haqiqiy pul o'tkazmasi kodda amalga oshirilmaydi** — Ping tashqi tizim,
bot faqat uning webhook orqali yuborgan holat o'zgarishlarini yozib boradi.

### B.2 Taxminiy oqim

1. Yangi SaaS mijoz ro'yxatdan o'tganda -> Ping'da customer/subscription
   yaratiladi (qaysi API chaqiruv — Ping hujjati kelmaguncha noma'lum).
2. Ping to'lov holatini **webhook** orqali botga yuboradi (`web/` ichida
   yangi `/api/webhooks/ping` route — imzo tekshiruvi Ping'ning HMAC
   sxemasiga bog'liq, hozircha noma'lum).
3. Webhook handler `billing_events`ga yozadi (idempotent —
   `ping_event_id` UNIQUE orqali takror qayta ishlanishning oldi olinadi),
   so'ng `subscriptions.status`ni yangilaydi.
4. `status != active` bo'lsa: yangi middleware (`middlewares/subscription_gate.py`,
   hali yo'q) tegishli `organization_id`ga tegishli barcha bot
   so'rovlarini bloklaydi, foydalanuvchiga "obuna muddati tugagan" xabari
   bilan — TZning "tizim AVTOMATIK O'CHADI" talabi shu middleware orqali.

### B.3 Ochiq savollar (Ping shartnoma kelgach hal qilinadi)

- Webhook autentifikatsiya usuli (HMAC imzo, IP allowlist, boshqa?).
- Grace period bormi (masalan 3 kun) yoki `past_due` darhol `suspended`ga
  aylanadimi?
- Bitta obuna butun tashkilotni yopadimi (C-qismdagi `organization_id`
  darajasida) yoki xizmat turi bo'yicha qisman cheklash bormi?

---

## C. Obuna va multi-tenant tayyorlik — SPEKULYATIV DIZAYN (15.1/15.2/16-band)

> **2-FAZA ISHI, HOZIR QURILMAYDI.** TZning o'zi "2-fazada amalga
> oshiriladi" deydi. Quyidagi reja faqat KATTA REFAKTORINGning shaklini
> belgilaydi — real boshlanish B-qism (Ping) tasdiqlangandan keyin, alohida
> sessiyada.

### C.1 Nega hozir emas

Deyarli har bir jadvalga (`departments`, `employees`, `tasks`, `leads`,
`clients`, ...) `organization_id` FK qo'shish va **har bir** repository
so'rovini shu bilan filtrlash kerak — bu yuzlab kichik o'zgarishdan iborat
katta, xatoga moyil refaktoring. Bitta xato joy = boshqa tashkilotning
ma'lumotini ko'rsatish (jiddiy xavfsizlik nuqsoni). TZ buni tan olib,
ataylab keyingi fazaga qoldirgan.

### C.2 Taxminiy migratsiya tartibi (2-faza boshlanganda qayta ko'rib
chiqiladi, hozir FAQAT reja)

1. `organizations` jadvali (`id`, `name`, `created_at`) — birinchi yangi
   jadval.
2. Nullable `organization_id` FK barcha "top-level" jadvallarga
   (`departments`, `employees`, `clients`) qo'shiladi (server_default
   YO'Q — mavjud qatorlar uchun bitta martalik data-migration skripti
   bilan yagona "Melores Mebel" tashkilotiga bog'lanadi, keyin NOT NULL
   qilinadi).
3. Bog'liq jadvallar (`tasks`, `leads`, ...) `organization_id`ni
   to'g'ridan-to'g'ri emas, ota jadvali orqali (`department.organization_id`)
   oladi — takrorlanmasin.
4. Har bir repository metodiga `organization_id` parametri qo'shiladi;
   `handlers/`dagi har bir chaqiruv joriy foydalanuvchining tashkiloti bilan
   chaqiradi (middleware orqali `employee.organization_id`dan olinadi).
5. Bu qadam **TO'LIQ tugagunga qadar** yangi SaaS mijoz qo'shib bo'lmaydi
   — hozircha faqat bitta tashkilot (Melores Mebel) bor, shu sabab hech
   qanday shoshilinch yo'q.

### C.3 Ochiq savollar

- Trello: har bir tashkilot o'z Trello akkountiga ega bo'ladimi (alohida
  API key/token, `organizations` jadvalida saqlanadi) yoki bitta umumiy
  akkountda ko'p board? TZda ko'rsatilmagan.

---

## D. Video darslar bo'limi — SPEKULYATIV DIZAYN (15.2-band)

> **2-FAZA ISHI.** Ichki Melores Mebel jamoasi uchun EMAS — kelajakdagi
> SaaS mijozlar (boshqa mebel sexlari) uchun o'quv materiali.

TZ matni: "O'rgatish: KO'CHIRIB BO'LMAYDIGAN video darslar Telegram
(himoyalangan kanal) yoki sayt ichiga joylanadi; mijoz kirib tartib bilan
ko'radi."

### D.1 Ikki texnik variant (ikkalasi ham to'liq nusxa-himoyasini
kafolatlamaydi — screen recording doim mavjud, TZning o'zi buni tan olishi
kerak bo'ladi, ochiq savol sifatida qoldiriladi)

| Variant | Ishlash tartibi | Cheklov |
|---|---|---|
| Telegram himoyalangan kanal | "Forward taqiqlangan" (`protect_content`) xususiyatli yopiq kanalga video yuklanadi, mijoz kanalga taklif qilinadi (obuna faol bo'lgunicha) | aiogram allaqachon loyihada bor — yangi tashqi bog'lanish shart emas (ponytail: mavjud vositadan foydalanish) |
| Web streaming | `web/`ga video player sahifa, video fayllar yuklab olinmaydigan tarzda (masalan signed URL, cheklangan muddat) berib boriladi | yangi infratuzilma (video storage/CDN) kerak, `web/`ning hozirgi "faqat statistika ko'rish" doirasidan tashqari |

**Tavsiya (2-faza boshlanganda qayta tasdiqlanadi)**: Telegram varianti —
mavjud bot infratuzilmasini ishlatadi, yangi storage/CDN qo'shmaydi,
`protect_content=True` allaqachon Bot API'da bor (kod darajasida arzon).

### D.2 Ochiq savollar

- Kanalga kirish obuna holatiga (B-qism) bog'lanadimi (obuna to'xtasa
  kanaldan chiqariladimi)? Texnik jihatdan oson (`kickChatMember` keyin
  qayta taklif), lekin biznes qarori kerak.

---

## Yakuniy xulosa

**A qismi** — bajarishga tayyor: `bot/_smoke_e2e_full.py` va
`bot/railway.json` yozilgan, Railway xizmatini sozlash va E2E skriptni
ishga tushirish qolgan operatsion qadamlar (kod emas, deploy/infra
harakati).

**B/C/D qismlari** — spekulyativ texnik dizayn hujjatlashtirilgan (yuqorida),
lekin **hech qanday kod yozilmagan va yozilmaydi** Ping shartnomasi
tasdiqlanmaguncha (TZ 19-band #13). Bu dizaynlar 2-faza boshlanganda
qayta ko'rib chiqiladi — Ping'ning haqiqiy API shakli ma'lum bo'lgach
B-qism deyarli aniq o'zgaradi.

## Ochiq savollar (2-faza boshlanishidan oldin, TZ 19-band)

1. SaaS obunaning narxi va Ping billing shartnomasi tafsilotlari (#13) —
   BOSHQA hamma narsadan oldin hal qilinishi kerak.
2. Ping webhook autentifikatsiya usuli, grace period siyosati (B.3).
3. Multi-tenant Trello akkount modeli (C.3).
4. Video darslar — obuna holatiga bog'lanishi (D.2).

## Tekshirish rejasi

- **A**: `bot/_smoke_e2e_full.py` (yuqorida tavsiflangan, ishga tushirish
  qolgan) + production'ga chiqarilgandan keyin bir necha kunlik kuzatuv
  davri (log monitoring) — avtomatlashtirilgan test emas, operatsion
  nazorat.
- **B/C/D**: 2-faza rejalashtirilganda, Ping shartnomasi tasdiqlangach,
  alohida aniqlanadi — bu hujjatdagi dizayn boshlang'ich nuqta, yakuniy
  reja emas.
