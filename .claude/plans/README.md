TZ 17-band rasmiy jadvali:

| Etap | Bosqich | Mazmuni | Holat |
|---|---|---|---|
| 1-etap | 1-bosqich | Xodimlar bazasi + Trello board/karta tuzilishi + asosiy bot (vazifa berish/qabul, ishchi oynasi, ko'p bosqichli progressiya) | Bajarilgan, real infratuzilmada sinovdan o'tgan |
| 1-etap | 2-bosqich | Muddat/taymer va rang avtomatikasi; eslatmalar jadvali (09:00/13:00/15:00/17:00/18:00); "Stop" funksiyasi va signallar | Ishlanmoqda: 02-muddat-eslatma-stop.md |
| 2-etap | 3-bosqich | KPI: minus/plus ball, brigadir ulushi, checklist jarayoni | Navbatda: 03-kpi-ball-tizimi.md |
| 2-etap | 4-bosqich | Statistika/dashboard, oylik eng yomon/eng yaxshi reytinglar, Telegram hisobotlar, mijoz xabarnomalari | Navbatda: 04-statistika-dashboard.md |
| 3-etap | 5-bosqich | Sotuv CRM (Ezza + Melores), qo'ng'iroqlar bazasi, lid eslatmalari | Navbatda: 05-sotuv-crm.md |
| 3-etap | 6-bosqich | Umumiy test, ishga tushirish; SaaS tayyorgarlik: billing (Ping), obuna, video darslar | Navbatda: 06-test-va-saas.md |

Ishlash tartibi: har bir bosqich to'liq amalga oshirilib, real infratuzilmada
(Railway Postgres + Trello "Test" board, hech qachon "Fasad seh" production
board emas) sinovdan o'tkazilgandan keyingina navbatdagi bosqichga o'tiladi —
bu loyihada avvaldan o'rnatilgan qat'iy tartib (CLAUDE.md ga qarang). Har
bosqich ichida ham qismlar (A/B/C/D...) ketma-ket bajariladi, parallel emas.

Har bosqich tugagach: shared/db-schema.md bosqichma-bosqich yangilanadi
(hammasi oxirida emas); ishlatilgan vaqtinchalik smoke-test skriptlari
(bot/_smoke_*.py) o'chiriladi; ushbu papkadagi mos fayl holati "Bajarilgan"
ga yangilanadi.

Muhim eslatmalar (barcha bosqichlarga tegishli):
- Avtomatik test suite yo'q — tekshirish har doim real DB/Trello'ga qarshi
  bitta martalik skript orqali (CLAUDE.md > Commands).
- Sozlanuvchanlik talabi (16-band): eslatma vaqtlari, jarima qiymatlari, ball
  ulushlari — hech biri kodga qattiq yozilmasin, admin paneldan
  o'zgartiriladigan bo'lsin.
- Ochiq savollar (TZ 19-band) ba'zi bosqichlarni to'g'ridan-to'g'ri
  bloklaydi (masalan brigadir ulushi aniq foizi, plus ball mezonlari,
  checklist matn formati). Bunday joylarda taxmin qilinmaydi —
  foydalanuvchidan aniq javob so'raladi.
- Layering buzilmasin: handlers/ -> services/ -> db/repositories/ ->
  db/models/, bitta yo'nalishda. Har servis funksiyasi — alohida Unit of
  Work (async_session() ochadi, commit() qiladi).
