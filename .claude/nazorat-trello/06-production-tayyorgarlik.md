# 6. Production tayyorgarlik va test

## 6.1. Mini App static fayllar keshlash muammosi — ✅ TUZATILDI (2026-07-31)

**Muammo edi**: `bot/miniapp/server.py`'da `app.router.add_static("/",
PUBLIC_DIR, show_index=False)` va `_index` handleri hech qanday
`Cache-Control` header'i yubormas edi. Telegram Mini App WebView'i
statik fayllarni (JS/CSS) o'z heuristikasi bilan qattiq keshlaydi —
natijada Railway'ga deploy qilingandan keyin ham foydalanuvchi eski
`app.js`ni ko'rib turardi. Telegram'ni fon/oldinga o'tkazish yetmasdi,
uni **to'liq yopib qayta ochish** kerak bo'lardi (haqiqatan uchragan
holat).

**Tuzatish**: `miniapp/server.py`'ga `no_cache_middleware` qo'shildi va
root ilovaga ulandi. Har javobga `Cache-Control: no-cache` qo'yadi
(`setdefault` — handler o'zi aniq qiymat qo'ysa, ustidan yozilmaydi).

Nega `no-cache`, `no-store` emas: `no-cache` = "keshla, lekin
ISHLATISHDAN OLDIN serverdan so'ra". `FileResponse` `Last-Modified`/`ETag`
yuborgani uchun fayl o'zgarmagan bo'lsa javob bo'sh `304` bo'ladi (arzon
— har safar butun faylni qayta yuklamaydi), o'zgargan bo'lsa darhol
yangisi keladi. `no-store` bo'lsa har safar to'liq qayta yuklanardi.

Root ilovaga ulangani uchun statik fayllarni ham, `/api/miniapp/*` JSON
javoblarini ham qamrab oladi — API javoblari ham keshlanmasligi kerak
(ball/vazifa holati doim yangi bo'lsin).

**Test**: `bot/tests/test_miniapp_cache_headers.py` (oddiy
`python tests/test_miniapp_cache_headers.py`, bazasiz/Telegramsiz —
soxta bot bilan localhost'da ilova ko'tariladi). Uchta holatni
tekshiradi: `/` (index), `/js/app.js` (statik), `/api/miniapp/me` (API).
Testning haqiqiyligi tasdiqlangan — middleware o'chirilganda
`AssertionError: None` bilan yiqiladi.

> Eslatma: bu tuzatish **ikkala modul uchun ham** amal qiladi (server
> umumiy). Mebel ("Fasad seh") xatti-harakatiga ta'sir qilmaydi — faqat
> HTTP header, hech qanday mantiq o'zgarmagan.

## 6.2. To'liq end-to-end test — 01-band bajarilishini kutmoqda

`01-haqiqiy-zanjir-yaratish.md`ning 1.5-bandi (xodim biriktirish +
bo'lim↔list moslashtirish) bajarilgach, to'liq hayotiy tsiklni sinash
kerak: buyurtma yaratish (STOPPED holatda) → "joy tayyor" (resume) →
Kontrol → ... → fork → 3 filial → join → ... → Montaj.

Bu — kod emas, **haqiqiy foydalanish sinovi**. Rahbar Mini App orqali
o'zi sinashini aytdi (2026-07-31). Sinov uchun demo board tayyor:
`Nazorat Trello demo` (`https://trello.com/b/Y3eXUO8Q/nazorat-trello-demo`)
— haqiqiy "nazorat trello" boardining 51 listi nusxalangan, kartasiz.

**Bloklovchi**: 17 ta `fasad_sex` bo'limining hech birida faol xodim
yo'q. Batafsil — `01-haqiqiy-zanjir-yaratish.md` §1.5.

## 6.3. Monitoring — ✅ MAVZU YO'Q (2026-07-31)

Avval bu band `daily_report_job`ni (Phase 8) Railway loglarida kuzatishni
tavsiya qilardi. **O'sha job endi mavjud emas** — kunlik rasm/video
hisobot funksiyasi rahbar talabiga ko'ra 2026-07-31'da koddan butunlay
o'chirildi (`05-tz-ochiq-savollar.md`ga qarang). Kuzatadigan narsa yo'q.

Hozirgi rejalashtirilgan job'lar: `daily_sync_job` (kunlik),
`overdue_watch_job` (soatlik), `reminder_job`/`report_job` (sozlamadan),
`lead_follow_up_job` (kunlik), `trello_ingest_job` (5 daqiqada —
**faqat mebel**, `fasad_sex`ga tegishli emas).

## 6.4. `overdue_watch_job`/`daily_sync_job` — Fasad sex bilan ishlashi

Bu ikki job **umumiy** (department-agnostic) — `fasad_sex` bo'limlarida
vazifa paydo bo'lgach, ular avtomatik shu vazifalarni ham qamrab oladi,
alohida kod o'zgarishi kerak emas. Faqat 6.2 (birinchi haqiqiy tsikl)
o'tgach, birinchi overdue/label-sync aylanishida loglarni kuzatib ko'rish
tavsiya etiladi.

> Bu band ham 6.2 kabi xodim biriktirilishini kutmoqda — hozircha
> `fasad_sex` bo'limlarida birorta ham vazifa yo'q, ya'ni job'lar u yerda
> hech narsa qilmayapti.

## 6.5. Ikkinchi zavod uchun alohida Trello token — ✅ KERAK EMAS (2026-07-31)

Rahbar javobi (`05-tz-ochiq-savollar.md` #1): **ikkala zavod ham Toshkent
shahrida, bitta Trello workspace ichida.**

Demak bo'lim darajasida board/token tanlash logikasi **kerak emas** —
`TrelloClient` hozirgidek bitta global `TRELLO_API_KEY`/`TRELLO_TOKEN`ga
(`config.settings`) tayanaveradi. Bu eng katta potensial arxitektura ishi
edi, endi yopildi.

## Qisqa holat

| Band | Holat |
|---|---|
| 6.1 Cache-Control | ✅ Tuzatildi + test yozildi |
| 6.2 E2E test | ⏳ Xodim biriktirilishini kutmoqda (01 §1.5) |
| 6.3 Monitoring | ✅ Mavzu yo'q (job o'chirilgan) |
| 6.4 Job'lar Fasad sex bilan | ⏳ 6.2 bilan birga (kod o'zgarishi kerak emas) |
| 6.5 Alohida Trello token | ✅ Kerak emas (bitta workspace) |

Ya'ni **kod tomondan 6-bo'limda qiladigan ish qolmadi**. Qolgan ikki band
(6.2, 6.4) — kod emas, haqiqiy foydalanish sinovi, va ikkalasi ham
`01`-bandning xodim biriktirish qadamiga bog'liq.
