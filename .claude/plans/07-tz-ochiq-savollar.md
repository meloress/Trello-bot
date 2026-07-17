# TZ 19-bandning ochiq savollari — konsolidatsiyalangan holat

Holat: KUZATUV RO'YXATI (kod emas — bu hujjat faqat holatni kuzatadi, har
bir savol o'z tabiatiga ko'ra yopiladi).

TZning o'zi 19-bandda "ishni boshlashdan oldin aniqlashtirish SHART" deb
belgilagan 13 ta savol bor edi. 2026-07-17 audit natijasida ularning
holati quyidagicha:

| # | Savol | Holat |
|---|---|---|
| 1 | Checklist qanday to'ldiriladi — tugma orqalimi yoki erkin matnmi? | ✅ HAL QILINDI: bo'lim zanjiri bo'yicha avtomatik (har bosqich = 1 punkt), foydalanuvchi tasdiqlagan (02-bosqich hujjati) |
| 2 | Kechikish jarima jadvali va 8.5-band oylik surilish | ✅ HAL QILINDI: rasman tasdiqlangan, `penalty_rules`/`app_settings`da |
| 3 | Brigadir ulushi: 1/3 (0.33) mi, 30-50% mi? | ✅ HAL QILINDI: 0.33, `app_settings.brigade_share_ratio` orqali SOZLANADIGAN (o'zgarishi mumkin, kodga qattiq yozilmagan) |
| 4 | Plus ball mezonlari | ✅ HAL QILINDI: `plus_ball_per_day`/`plus_ball_max_days`, sozlanadigan |
| 4a | 8.3 (avto brigadaga o'tkazish) qaysi yo'nalishlarda yoqilgan? | ✅ ARXITEKTURA TAYYOR: `departments.auto_reassign_after_48h` har bo'lim uchun alohida yoqiladi/o'chiriladi (`/autoreassign`). Aniq RO'YXAT — qaysi bo'limlar uchun ON qilinishi — operatsion qaror, admin panel orqali istalgan vaqt o'zgartiriladi, bloklovchi emas |
| 4b | 8.6 faqat bayroqlanadimi yoki summa ham hisoblanadimi? | ✅ HAL QILINDI: faqat bayroqlash + qo'lda summa kiritish (`/moliyaviy`, `/avanskechirim`) — to'liq moliya moduli 18-band bo'yicha keyingi fazaga qoldirilgan |
| 5 | Eslatma vaqtlari: 09/13/15/17/18 mi, 11/18 mi? | ✅ HAL QILINDI: SOZLANADIGAN (`app_settings.reminder_schedule`), default 09:00/13:00/15:00/17:00 (18:00 "DEDLAYN" alohida reminder sifatida emas — har task o'z `deadline`iga nisbatan soatlik tekshiriladi, 02-bosqich hujjatida asoslangan) |
| 6 | Stop paytida taymer to'liq to'xtaydimi? | ❌ HALI HAL QILINMAGAN — hozircha kechikish `deadline`dan hisoblanadi, stop davri AYIRILMAYDI. Ishlaydi, lekin biznes tomonidan rasman tasdiqlanmagan |
| 7 | Qo'ng'iroq yozuvlari qayerdan — IP-telefoniya bormi? | ✅ HAL QILINDI: qo'lda kiritish (matn/ovozli xabar), IP-telefoniya ATAYLAB qurilmagan (provayder tanlanmagan) |
| 8 | "Uzoq aloqasiz" mijoz uchun necha kun? | ✅ HAL QILINDI: 7 kun, `app_settings.lead_follow_up_threshold_days` orqali sozlanadigan |
| 9 | Xodimlar soni/boardlar hajmi (Trello tarifi uchun)? | ⚠️ BIZNES QARORI — dasturiy ta'minotga aloqasi yo'q, kod tomondan hech qanday bloker yo'q |
| 10 | Laminoks (raspil) bo'limi qachon ochiladi? | ⚠️ BIZNES QARORI — arxitektura tayyor ("yangi bo'lim qo'shish tizim tuzilishini o'zgartirmaydi", 16-band talabi bajarilgan), istalgan vaqt yangi `departments` qatori sifatida qo'shilishi mumkin |
| 11 | Mijoz xabarnomasi kanali: Telegram, SMS, ikkalasimi? | ✅ HAL QILINDI: faqat Telegram, SMS ATAYLAB qurilmagan |
| 12 | Oylik "eng yomon" reytingi avtomatik guruhga tashlanadimi? | ❌ HALI HAL QILINMAGAN — ma'lumot mavjud (`/stats`, web "Reyting" modali), lekin avtomatik guruhga post qilish YO'Q, qo'lda screenshot ham yo'q (funksiya yo'q) |
| 13 | SaaS obuna narxi va Ping shartnoma tafsilotlari? | ❌ BLOKLANGAN — 2-faza boshlanishidan oldin biznes tomonidan hal qilinishi SHART, `08-saas-tayyorgarlik.md`ga qarang |

## Amaliy xulosa

13 tadan **9 tasi hal qilingan** (kodda mos yechim bilan), **2 tasi biznes
qarori** (koddan mustaqil, hech narsani bloklamaydi), va **faqat 2 tasi
haqiqiy ochiq**:

- **#6** (Stop paytida taymer to'xtaydimi) — kod ishlaydi (hozirgi default:
  yo'q, to'xtamaydi), lekin rasmiy tasdiq yo'q. Agar javob "ha, to'xtaydi"
  bo'lsa — `penalty_service.calculate_and_apply_task_penalty()` va
  `task_service.reassign_task_brigade()`dagi `hours_late` hisoblashiga
  stop/resume oralig'ini ayirish kerak bo'ladi (kichik, aniq o'zgarish).
- **#12** (oylik reyting avtomatik guruhga) — agar javob "ha, bot o'zi
  yuborsin" bo'lsa, yangi oylik job kerak (`jobs/report_job.py`ga
  qo'shimcha funksiya, mavjud `run_monthly()` naqshida, farqi — bitta
  belgilangan guruh chatiga yuboriladi, `app_settings`ga
  `ranking_group_chat_id` qo'shilishi kerak bo'ladi).

## Tugagach

Har bir savol rasman javob olgach, shu qatordagi holat yangilanadi. Barcha
qatorlar ✅ bo'lgach, bu hujjat `.claude/plans/`dan olib tashlanadi
(`shared/db-schema.md`/`CLAUDE.md`ga tegishli joylarda yakuniy qarorlar
qayd etiladi).
