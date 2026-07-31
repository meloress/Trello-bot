# 5. TZning o'z ochiq savollari — ✅ HAMMASI YOPILDI (2026-07-31)

Barcha 14 savolning yakuniy holati shu yerda (avval `.claude/plans/`dagi
alohida faylda kuzatilar edi — o'sha papka 2026-07-31'da o'chirildi,
chunki mebel moduli tugagan; tarixi git'da qoldi).

## Zanjir yaratishni bloklaydigan savollar — hammasi hal bo'ldi

1. ✅ **Ikkinchi zavod qaysi shaharda, alohida Trello workspace kerakmi?**
   Rahbar javobi: **ikkalasi ham Toshkent shahrida, bitta Trello
   workspace ichida**. Alohida workspace kerak emas — ya'ni
   `TrelloClient`ning bitta global token/key'i yetarli, bo'lim darajasida
   board/token tanlash logikasi KERAK EMAS (bu eng katta arxitektura
   xavfi edi, endi yopildi). Zanjirning o'zi hali yaratilmagan (1-zavod
   amalda ishga tushmaguncha kutiladi) — `01-haqiqiy-zanjir-yaratish.md`
   1.4-band.

2. ✅ **"Gip-lab" va boshqa noaniq atamalar** (Municipal, Leyechon,
   Bindoq, Grubogororya, Savina) — **bosqich/brigada EMAS, yopildi**.
   Haqiqiy production boardda (`nazorat trello`,
   `https://trello.com/b/fOC82usT/nazorat-trello`) empirik tekshirildi:
   **49 ta list nomi va 4029 ta karta nomida bu atamalarning bittasi ham
   uchramaydi** (skript orqali, har bir atama + imlo variantlari bilan).
   Ya'ni bular ish jarayonining bosqichlari emas — TZ suhbatidan qolgan
   og'zaki iboralar (masalan "Grubogororya" ≈ ruscha "грубо говоря" =
   "qo'pol qilib aytganda"; "doq kelyapti" — bo'yoqdagi dog', alohida
   bosqich emas). Rahbar tasdiqladi: **zanjirga hech narsa qo'shilmaydi.**
   > Eslatma: "Gip-lab" bunga KIRMAYDI — u haqiqiy bosqich va boardda
   > ham bor (`GIPLAB Abdulloh 24`), DB'da ham bor (id 77).

3. ✅ **Shpon→Shkurka→Kraska va Malyarka bir xil jarayonmi yoki
   ikkitami?** — **bitta ketma-ket zanjir**, boarddan empirik
   tasdiqlandi. Haqiqiy board listlari aynan shu tartibda joylashgan:
   `Shpon sehta yasalvotti 15 sutka` → `Shkurkada` → `Shkurkadan chiqqan
   zakazla (stopda)` → `kraska seh 72 soat` → `Malyarka sklad Qurish va
   O'rash 24 soat`. DB'dagi zanjir allaqachon xuddi shunday
   (84 Shpon → 85 Shkurka → 86 Kraska → 87 Malyarka) — **o'zgartirish
   kerak emas.**

## Qolgan savollar — hammasi javob oldi

4. ✅ **Kontrol 1 yoki 2 kishi** — operatsion tanlov, kodga ta'siri yo'q
   (har safar rahbar o'zi hal qiladi). O'zgarishsiz.

5. ✅ **Kunlik hisobot topshirmaslik jarima keltiradimi?** — Rahbar
   javobi: **kunlik rasm/video umuman kerak emas.** Ya'ni savol jarima
   haqida emas, butun funksiya haqida hal bo'ldi. **Funksiya koddan
   butunlay o'chirildi (2026-07-31)** — batafsil quyida.

6. ✅ **Ustanovkachi/svarshik MISC toifasi chegarasi** — admin qo'lda
   tanlaydi (`MiscCategory` enum: office/fasad_sex/installer/welder,
   Mini App'da o'zbekcha nomlari bor: "Ofis xodimlari"/"Fasad sex"/
   "O'rnatuvchilar"/"Payvandchi"). Ishlaydigan standart, bloklovchi emas.

7. ✅ **Kunlik norma "actual" qanday o'lchanadi (kv.m yo'q)?** — Rahbar
   javobi: **hozircha vazifa soni yetarli.** `stats_service.get_capacity_vs_actual()`
   yakunlangan-vazifa-soni proksisini ishlatishda davom etadi, `tasks`ga
   kv.m ustuni QO'SHILMAYDI. Bu statistika baribir faqat ko'rsatkich —
   hech qachon jarima uchun ishlatilmaydi.

8. ✅ **Fork paytida Trello karta qaysi list'da qoladi?** — Rahbar
   tasdiqladi: **fork nuqtasida qolsin (hozirgi kod xatti-harakati).**
   Karta "Fayl yig'ish"da turadi, 3 parallel tarmoq "Bosqichlar"
   checklistida ko'rinadi, join bo'lgach bir marta "Korpus sexi"ga
   ko'chadi. Kod o'zgarmaydi.

## Kunlik rasm/video hisobot — koddan o'chirildi (2026-07-31)

Rahbar "umuman kerak emas" degani uchun butun funksiya olib tashlandi.
Xavfsiz edi, chunki **production'da hech qachon ishlatilmagan**:
o'chirishdan oldin DB'da 0 ta hisobot yozuvi va 0 ta xodimda yoqilgan
bayroq bor edi.

O'chirilgan fayllar (5 ta, 264 qator):
`services/daily_report_service.py`, `jobs/daily_report_job.py`,
`handlers/common/daily_report.py`, `db/models/daily_report_submission.py`,
`db/repositories/daily_report_submission_repo.py`.

Tozalangan joylar: `main.py` (router + job rejasi), `db/models/__init__.py`,
`db/repositories/__init__.py`, `db/repositories/employee_repo.py`
(`list_daily_report_required()`), `services/notification_service.py`
(`notify_daily_report_request()`), `services/settings_service.py`
(`daily_report_time` snapshot maydoni), `miniapp/api/admin.py`
(`GET /daily-reports` route + xodim maydoni + sozlama), `app.js`
(nav-tugma + `screenDailyReports` + xodim checkbox'i + sozlama maydoni),
`i18n.js` (uz + ru labellar).

**DB tegilmadi** — `daily_report_submissions` jadvali va
`employees.daily_report_required` / `app_settings.daily_report_time`
ustunlari joyida qoldi (ikkalasida ham `server_default` bor, shuning
uchun modeldan olib tashlash xavfsiz). Bu 8.6-band "Moliyaviy takliflar"
o'chirilishi bilan bir xil naqsh — jadval/ustun tashlash kerak bo'lsa,
alohida so'ralgan Alembic migratsiyasi kerak.

Tekshirildi: barcha modullar import bo'ladi, 3 ta standart test o'tadi,
JS sintaksisi to'g'ri, va real DB'da sozlama o'qish/yozish + xodim o'qish
ishlaydi.

## Holat

**Bu bo'lim yopiq — 14/14 savol javob oldi, ochiq qolgani yo'q.**
Kuzatib boriladigan narsa qolmagani uchun bu faylni keyingi tozalashda
papkadan olib tashlash mumkin (tarixi git'da saqlanadi).
