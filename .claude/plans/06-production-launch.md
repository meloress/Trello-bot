# Production'ga chiqarish (TZ 6-bosqich, A-qismi)

Holat: TAYYOR, ISHGA TUSHIRISH QOLDI. Kod/skript/deploy-config yozilgan
(2026-07-17), lekin hali ishga tushirilmagan — bot hali real "Fasad seh"
production Trello board'ida ishlamayapti, Railway'ga hali deploy
qilinmagan.

TZ manbasi: 17-band (6-bosqich: "umumiy test, ishga tushirish"), 16-band
(ishonchlilik: avtomatik backup/qayta ishga tushirish).

## Nima tayyor

### 1. Uchdan-uchga (E2E) smoke test — `bot/_smoke_e2e_full.py`

Butun ishlab chiqarish oqimini bitta ketma-ket skriptda tekshiradi:
buyurtma yaratish → `overdue_watch_job` orqali OVERDUE aniqlash → 8.3
avto-o'tkazish signali asosida qo'lda o'tkazish → kechikish jarimasi →
ko'p bosqichli progressiya (2-bosqichga o'tish) → muddatidan oldin
yakunlash (plus ball) → mijoz xabarnomasi → statistika → davriy hisobot →
tozalash.

**Oldindan shart** (Test board'da qo'lda tayyorlanishi kerak):
- Kamida ikkita `next_department_id` bilan zanjirlangan bo'lim, ikkalasida
  ham `trello_list_id` sozlangan.
- Har ikkala bo'limda kamida bitta faol brigada, xodimlari bilan.

**Ishga tushirish:**
```bash
cd bot && .venv\Scripts\python _smoke_e2e_full.py
```
Muvaffaqiyat: oxirida `Phase 6-A E2E smoke test OK`. Ishlatilgach o'chiriladi
(`rm bot/_smoke_e2e_full.py`, repo konvensiyasi).

> **Eslatma**: bu skript real Trello "Test" board'da karta yaratadi/
> ko'chiradi va real Telegram xabarlari yuboradi — ishga tushirishdan oldin
> yuqoridagi shart bajarilganini tasdiqlang.

### 2. Railway deploy config — `bot/railway.json`

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
`restartPolicy` orqali yopiladi — alohida `systemd`/`pm2`/Docker supervisor
SHART EMAS.

## Qolgan qadamlar (operatsion, kod emas)

### A. E2E testni ishga tushirish
Yuqoridagi oldindan shartlarni Test board'da tayyorlab, skriptni ishga
tushirish. Xato chiqsa — qaysi qadamda to'xtaganini ko'rsatadi, shu
servisga qarab tuzatiladi.

### B. Railway'ga deploy (qo'lda, Railway dashboard)
1. Railway loyihasida yangi xizmat: "Deploy from GitHub repo", **Root
   Directory = `bot`**.
2. Environment Variables: `BOT_TOKEN`, `TRELLO_API_KEY`, `TRELLO_TOKEN`,
   `DATABASE_URL` (bir loyihada bo'lsa Railway avtomatik taklif qiladi).
3. Deploy qilish, loglarni kuzatish (`python main.py` xatosiz,
   `Update received` yozuvlari polling ishlayotganini bildiradi).
4. Ixtiyoriy: `web/` uchun ham alohida xizmat (Root Directory = `web`,
   start command `npm start`, `WEB_ADMIN_PASSWORD`/`WEB_SESSION_SECRET`).

### C. Production Trello board'larga o'tish
`departments.trello_list_id` (va agar sotuv ham ishga tushirilsa
`app_settings.sales_board_lists`) qiymatlarini Test board'dan haqiqiy
production board'larga ("Fasad seh", "Ezza sotuv", "Melores Mebel sotuv")
qo'lda UPDATE qilish (mavjud konvensiya — bot UI orqali emas). Oldin
Railway Postgres backup/snapshot olish tavsiya etiladi. Rollback:
`trello_list_id`ni Test board'ga qaytarib botni to'xtatish yetarli.

### D. Kuzatuv davri
Avtomatlashtirilgan test emas — production'ga chiqqandan keyin bir necha
kun Railway loglarini kuzatish, kamida bitta to'liq kunlik eslatma/hisobot
sikli ishlaganini tasdiqlash.

## Tavsiya etilgan tartib

1-5 raqamli hujjatlardagi (aniqlangan bo'shliqlar) tuzatishlar bu bosqichdan
OLDIN yopilishi tavsiya etiladi — ayniqsa 01 (Stop izohi) va 02 (label
holatlari), chunki ular production'dagi kunlik ishlatishga bevosita
ta'sir qiladi. Lekin bu qattiq bog'liqlik emas — E2E test va Railway deploy
mustaqil ravishda ham bajarilishi mumkin.

## Tugagach

- Ushbu hujjat `.claude/plans/`dan olib tashlanadi, README'dagi qator ham.
- `CLAUDE.md`dagi Phase 6 tavsifi "ishga tushirildi" deb yangilanadi.
