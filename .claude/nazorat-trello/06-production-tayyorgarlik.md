# 6. Production tayyorgarlik va test

## 6.1. Mini App static fayllar keshlash muammosi (bugun aniqlangan)

`bot/miniapp/server.py`'da `app.router.add_static("/", PUBLIC_DIR,
show_index=False)` — hech qanday `Cache-Control` header'i yo'q. Telegram
Mini App WebView'lari statik fayllarni (JS/CSS) o'zicha keshlaydi, va
aiohttp default'da eski nusxani qayta berishi mumkin. Natija: har safar
deploy qilinganda, foydalanuvchilar yangi kodni ko'rish uchun Telegram'ni
to'liq yopib qayta ochishlari kerak bo'lmoqda (bugun aynan shu muammo
uchrадi).

**Tuzatish**: statik javoblarga `Cache-Control: no-cache` (yoki qisqa
`max-age`) header qo'shish, `_index`/`add_static` javoblariga. Kichik,
xavfsiz o'zgarish — xohlasangiz hoziroq bajarib beraman.

## 6.2. To'liq end-to-end test (haqiqiy zanjir yaratilgach)

`01-haqiqiy-zanjir-yaratish.md` bajarilgach, mavjud
`bot/_smoke_e2e_full.py` andozasida (lekin Fasad sex zanjiri uchun)
to'liq hayotiy tsiklni sinab ko'rish kerak: buyurtma yaratish (STOPPED
holatda) → "joy tayyor" (resume) → Kontrol → ... → fork → 3 filial →
join → ... → Montaj. Bu — kod emas, balki **haqiqiy foydalanish sinovi**,
`.claude/plans/06-production-launch.md`dagi mavjud rejaga o'xshash, lekin
Fasad sex uchun.

## 6.3. Monitoring — yangi kunlik job

`daily_report_job` (Phase 8) endi har kuni ishga tushadi
(`app_settings.daily_report_time`, standart 09:00). Birinchi bir necha
kun ichida Railway loglarida bu job xatosiz ishlayotganini tekshirish
tavsiya etiladi (yangi kod, hali production'da haqiqiy tsiklda
sinalmagan).

## 6.4. `overdue_watch_job`/`daily_sync_job` — Fasad sex bilan ishlashi

Bu ikki job allaqachon **umumiy** (department-agnostic) — Fasad sex
bo'limlari yaratilgach, ular avtomatik shu bo'limlarni ham qamrab oladi
(alohida kod o'zgarishi kerak emas). Faqat zanjir yaratilgach, birinchi
overdue/label-sync tsiklida kuzatib ko'rish tavsiya etiladi.

## 6.5. Ikkinchi zavod uchun alohida Trello token/workspace (agar kerak bo'lsa)

Agar `05-tz-ochiq-savollar.md` #1-savoliga javob "ha, alohida Trello
workspace" bo'lsa — `TrelloClient` hozir bitta global
`TRELLO_API_KEY`/`TRELLO_TOKEN`ga tayanadi (`config.settings`). Bu holda
bo'lim darajasida board/token tanlash logikasi kerak bo'ladi — bu katta,
alohida loyihalash talab qiladigan ish, hozircha rejada yo'q.
