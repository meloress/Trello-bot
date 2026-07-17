# 5-bosqich: Sotuv bo'limi — soddalashtirilgan CRM (Ezza + Melores)

Holat: BAJARILGAN, real Railway Postgres + Trello "Test" board'da sinovdan
o'tgan (`bot/_smoke_phase5_sales.py`: lid yaratish -> bosqichlar bo'ylab
o'tkazish -> Trello list ko'chishi tasdiqlangan -> qo'ng'iroq yozuvi ->
yopish, keyin tozalangan — Telegram bot UI sinovisiz). TZda "3-etap,
5-bosqich": "Sotuv CRM (Ezza + Melores), qo'ng'iroqlar bazasi, lid
eslatmalari".

**Foydalanuvchi tasdiqlagan qarorlar (2026-07-17, quyidagi "Ochiq savollar"ga javoban)**:
1. Lidlar alohida `leads` jadvalida (pastdagi tavsiya tasdiqlandi) — `tasks`
   kengaytirilmadi.
2. Qo'ng'iroq yozuvlari — FAQAT qo'lda kiritish (Telegram matn/ovozli xabar).
   IP-telefoniya integratsiyasi ATAYLAB qurilmagan: hech qanday provayder
   tanlanmagan, provayder-siz webhook kodi sinovdan o'tkazib bo'lmaydigan
   "o'lik kod" bo'lardi. Provayder tanlanganda bu alohida, kattaroq
   loyihalash talab qiladigan ish (5-bosqich hujjatidagi "C" bo'limiga qarang).
3. "Uzoq vaqt aloqaga chiqilmagan" standart chegara — 7 kun
   (`app_settings.lead_follow_up_threshold_days`, `/settings` orqali
   o'zgartiriladi).
4. Trello list ID'lari (`sales_board_lists`) — `departments.trello_list_id`
   bilan bir xil naqsh: bot UI QURILMADI, to'g'ridan-to'g'ri bazada
   sozlanadi. Haqiqiy Ezza/Melores Trello boardlari hali yaratilmagan —
   admin ularni yaratib, list ID'larini `app_settings.sales_board_lists`ga
   qo'lda yozishi kerak (smoke test faqat vaqtinchalik Test board list'lari
   bilan ishlab, keyin tozalab qo'ydi).

TZ manbasi: 13-band to'liq (13.1 lidlar varonkasi, 13.2 qo'ng'iroqlar bazasi,
13.3 eslatmalar/nazorat), 6.1-band (Ezza/Melores boardlari), 3-band
(Sotuvchi roli).

## Hozirda kodda NIMA BOR

**Deyarli hech narsa.** `handlers/sales/__init__.py` bo'sh papka sifatida
mavjud (CLAUDE.md: "supervisor/, sales/ mavjud lekin bo'sh — hali
qurilmagan"). `main.py`da izoh bor: `# TODO: handlers/ ichidagi qolgan
routerlarni (sales) shu yerga qo'shish`. `Role.SELLER` enum'da bor
(`utils/enums.py`) lekin hech qanday handler/servis unga ishlov bermaydi.
Hech qanday `client`/`lead`/`call_log` jadvali yo'q.

Bu — birinchi bosqich bo'lib, MAVJUD ishlab chiqarish domenidan (buyurtma
-> bosqich -> KPI) TO'LIQ FARQLI YANGI DOMEN (lid -> varonka -> yopilish)
qo'shadi. Mavjud `tasks`/`task_assignments`/`penalty_service` mantig'i bu
yerga TATBIQ ETILMAYDI — sotuv o'z alohida jadval to'plamiga ega bo'ladi.

## A. Trello tuzilishi — Ezza va Melores boardlari (6.1-band)

TZ jadvali (6.1-band):
- **Ezza sotuv** board, "Ezza savdo bo'limi" yo'nalishi: Yangi lid -> Aloqa
  qilindi -> Taklif berildi -> Kelishildi -> Yopildi.
- **Melores Mebel sotuv** board, "Melores savdo bo'limi" yo'nalishi: xuddi
  shu bosqichlar.

Bu ikkala board mavjud `departments` tuzilishiga MOS TUSHADI (har biri —
alohida `Department` qatori, `trello_list_id`larsiz emas, balki har
varonka bosqichi o'z Trello list'iga ega bo'ladi — xuddi ishlab chiqarish
bo'limlari kabi). Lekin **lid varonkasi ishlab chiqarish bosqich zanjiridan
(`next_department_id`) farq qiladi**: lid "Yopildi/Bekor qilindi"da tugaydi,
ishlab chiqarishga o'xshab keyingi jismoniy bo'limga o'tmaydi.

**Muhim arxitektura qarori kerak**: lidlarni mavjud `tasks` jadvalida
(`task_type` ga yangi `LEAD` qiymat qo'shib) saqlashmi, yoki butunlay yangi
`leads` jadvali yaratishmi? Ikkala yondashuv ham CLAUDE.md'dagi
`native_enum=False` qoidasiga mos (yangi enum qiymati qo'shish arzon).

**Tavsiya (lekin foydalanuvchi bilan tasdiqlanishi kerak)**: alohida
`leads` jadvali — sabab: `tasks` jadvali endi `deadline`/`current_
department_id`/`previous_task_id` (bosqich zanjiri) kabi ishlab chiqarishga
xos ustunlarga ega, lid esa muddat/KPI jarima tizimiga umuman kirmaydi
(TZda lid uchun "kechikish jarimasi" tilga olinmagan). Bitta jadvalga
zo'rlab sig'dirish ko'plab NULL ustunlarga olib keladi.

### Yangi jadvallar (taklif, tasdiqlash kerak)
- `clients` — 4-bosqichdagi mijoz xabarnomasi bilan BOG'LIQ bo'lishi mumkin
  (4-bosqich hujjatidagi eslatmaga qarang: ikki marta migratsiya qilmaslik
  uchun struktura oldindan muvofiqlashtirilsin).
- `leads` — `id`, `client_id` (FK), `brand` (Ezza/Melores — enum yoki
  `department_id` orqali), `stage` (Yangi lid/Aloqa qilindi/Taklif
  berildi/Kelishildi/Yopildi/Bekor qilindi — enum, `native_enum=False`),
  `assigned_seller_id` (FK -> employees), `trello_card_id`,
  `created_at`/`updated_at` (`TimestampedBase` orqali avtomatik).
- `call_logs` — 13.2-band: `id`, `lead_id` (FK), `recorded_by_id` (FK ->
  employees), `content` (matn) yoki `audio_file_id` (Telegram file_id,
  audio yozuv bo'lsa), `called_at`, `created_at`/`updated_at`.

## B. Lidlar varonkasi (13.1-band)

- Yangi `services/sales_service.py` (mavjud servislar naqshida — bitta
  modul, klass emas): `create_lead()`, `advance_lead_stage()`,
  `close_lead(won: bool)`.
- Har bosqich o'zgarishida Trello karta mos list'ga ko'chiriladi
  (`trello.move_card_to_list()` — mavjud metod, qayta ishlatiladi).
- `handlers/sales/leads.py` (yangi) — Sotuvchi (`Role.SELLER`) uchun: yangi
  lid kiritish, bosqich o'zgartirish, o'z lidlari ro'yxati.

## C. Qo'ng'iroqlar bazasi (13.2-band)

TZ 19-band ochiq savol #7: "Qo'ng'iroq yozuvlari qayerdan keladi —
IP-telefoniya integratsiyasi bormi, yoki sotuvchi qo'lda yuklaydimi?" —
**BLOKLANGAN, tasdiq kerak**.

Agar qo'lda yuklash (eng oddiy, TZ "arzon yechim" printsipiga mos) deb
tasdiqlansa:
- `handlers/sales/leads.py`: "Qo'ng'iroq qo'shish" tugmasi — matn yoki
  audio (Telegram voice/audio message) qabul qiladi, `call_logs`ga yozadi.
- IP-telefoniya integratsiyasi tasdiqlansa — bu ALOHIDA, ancha kattaroq
  ish (webhook qabul qilish, provayder API'siga bog'lanish) — TZda provayder
  nomi ko'rsatilmagan, alohida texnik loyihalash kerak bo'ladi.

## D. Eslatmalar va nazorat (13.3-band)

TZ matni: "Uzoq vaqt aloqaga chiqilmagan mijozlar ro'yxati bot orqali
sotuvchiga avtomatik eslatma bo'lib boradi." TZ 19-band ochiq savol #8:
"'Uzoq vaqt aloqaga chiqilmagan' mijoz uchun aniq necha kunlik chegara?" —
**BLOKLANGAN, tasdiq kerak** (masalan 7 kun? 14 kun? — sozlanadigan qilish
tavsiya etiladi, 16-band talabiga mos: `app_settings`ga yoki alohida
sozlamaga qo'shish).

- Yangi `jobs/lead_follow_up_job.py` — kunlik, `call_logs.called_at`
  MAX(called_at) < chegara bo'lgan OCHIQ (yopilmagan) lidlarni topib,
  mas'ul sotuvchiga eslatma yuboradi (`notification_service`ga yangi
  `notify_lead_follow_up()` funksiyasi).
- "Rahbar qo'ng'iroqlar varonkasi bo'yicha sotuvchilarni saralab, aniq
  vazifalar taqsimlaydi" — bu QO'LDA jarayon, mavjud MISC vazifa moduli
  (9-band, `task_service` `task_type=misc`) orqali AMALGA OSHIRILISHI
  MUMKIN (yangi kod kerak emas — rahbar oddiy MISC topshiriq beradi,
  "X mijozga qayta qo'ng'iroq qil" matni bilan).

## Rol va ruxsatlar

`Role.SELLER` — "Telegram bot + Trello" kirish kanali (TZ 3-band jadvali).
`RoleAccessMiddleware({Role.SELLER})` mavjud middleware naqshida yangi
`handlers/sales/*.py` routerlariga qo'llanadi (`middlewares/auth.py`,
o'zgarishsiz qayta ishlatiladi).

## Ochiq savollar (hal qilindi, 2026-07-17 — yuqoridagi "Foydalanuvchi tasdiqlagan qarorlar"ga qarang)

1. ~~`leads` alohida jadvalmi yoki `tasks.task_type=lead` kengaytirilishimi~~ —
   alohida jadval tanlandi.
2. ~~Qo'ng'iroq yozuvlari manbai: qo'lda yuklashmi yoki IP-telefoniya
   integratsiyasi~~ (TZ 19-band #7) — qo'lda kiritish tanlandi, IP-telefoniya
   keyingi (provayder tanlanmagan) alohida ishga qoldirildi.
3. ~~"Uzoq vaqt aloqaga chiqilmagan" aniq kun chegarasi~~ (TZ 19-band #8) —
   7 kun, sozlanuvchan (`lead_follow_up_threshold_days`).
4. Xodimlar/boardlar hajmi — Trello tarif tanlovi uchun (TZ 19-band #9,
   sotuvga ham tegishli bo'lishi mumkin, umumiy loyihaviy savol) — HALI OCHIQ,
   bu bosqich kodi bilan bog'liq emas (Trello tarif — biznes/moliyaviy qaror).

## Migratsiya

Amalga oshirildi: `ff165aafd9b1` (`app_settings.lead_follow_up_threshold_days`,
`app_settings.sales_board_lists`) va `11e2c2cee985` (`leads`, `call_logs`
jadvallari), `b3f7a1c9d204`ning ustiga (4-bosqichda yaratilgan `clients`
qayta ishlatildi, qayta yaratilmadi). FK'lar: `fk_leads_client_id`, `fk_leads_
assigned_seller_id`, `fk_call_logs_lead_id`, `fk_call_logs_recorded_by_id`.

## Tekshirish rejasi — BAJARILDI

Real Railway Postgres + Trello **"Test" board**da (production Ezza/Melores
boardlari umuman qurilmagan hali, "Fasad seh" qoidasi shu sabab tabiiy
ravishda saqlanadi). `bot/_smoke_phase5_sales.py` (vaqtinchalik, ishlatilgach
o'chirilgan) orqali: lid yaratish -> `advance_lead_stage` (Trello karta
Test board'dagi vaqtinchalik "contacted" list'iga ko'chganini tasdiqladi,
`get_card` orqali tekshirildi) -> qo'ng'iroq yozuvi qo'shish -> `close_lead
(won=True)` (karta "Yopildi" list'iga ko'chdi) — hammasi muvaffaqiyatli.
Test uchun yaratilgan 5 ta vaqtinchalik Trello list arxivlandi, karta
o'chirildi, `sales_board_lists.ezza` standart (`NULL`) holatga qaytarildi,
DB test qatorlari (lead/call_log/client/seller) o'chirildi. Follow-up
job (`jobs/lead_follow_up_job.py`) mantiqan `LeadRepository.list_stale_open()`
ustida qurilgan (bir xil sinov qamrovida alohida sinalmadi — kodi
`overdue_watch_job` naqshining to'g'ridan-to'g'ri takrori).

**Hali qilinishi kerak (bu bosqich kodi tugagandan keyingi, operatsion qadam)**:
haqiqiy "Ezza sotuv" va "Melores Mebel sotuv" Trello boardlarini yaratish
(6.1-band, 5 tadan list bilan), so'ng ularning list ID'larini
`app_settings.sales_board_lists`ga qo'lda yozish — buni admin/dev to'g'ridan-
to'g'ri bazada bajaradi (`departments.trello_list_id` bilan bir xil, hech
qanday bot buyrug'i yo'q).
