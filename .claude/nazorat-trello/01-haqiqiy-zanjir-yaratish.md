# 1. Haqiqiy Fasad sex zanjirini yaratish

## ✅ 2026-07-24: asosiy zanjir yaratildi

17 ta department (module="fasad_sex", factory_name=NULL — bitta zavod),
yangi Trello board'da ("Fasad sex — Ishlab chiqarish", 17 list + "Stopda"),
DB'da to'liq chiziqli/fork/join bog'lanishlar bilan yaratildi va real
DB'ga qarshi smoke-test orqali tekshirildi (zanjir shakli + starts_stopped
+ auto-resume — barchasi OK). Kelishilgan qarorlar:

- Yangi, toza board (mavjud "Test"/"Fasad seh"ga tegilmadi).
- Bitta zavod hozircha (`factory_name=NULL`).
- Shpon→Shkurka→Kraska→Malyarka — bitta chiziqli ketma-ketlik.
- 7-band ("Ta'minot") va 8-band (material shabloni NAMUNASI) chain'ga
  KIRITILMADI — 7 o'zi "tizimga ta'siri yo'q" deb belgilangan, 8 esa
  1.3-band material-turi shablonining o'zi (pastga qarang, hali ochiq).
- Malyarka ichidagi 24 soatlik sub-bosqich hozircha ALOHIDA department emas.
- Sklad: `starts_stopped=True` + `stopped_auto_resume_after_hours=24`.
  **Bu kod o'zgarishini talab qildi** (avval `starts_stopped` faqat
  buyurtmaning ENG BIRINCHI bosqichida ishlar edi, Sklad esa mid-chain) —
  `task_service.activate_pending_stage()` endi buni ham qo'llab-quvvatlaydi,
  va `jobs/overdue_watch_job.py`ga yangi soatlik qism qo'shildi
  (`_process_stopped_auto_resume`). Migratsiya: `f3a7c1d9e4b6`. Batafsil:
  `shared/db-schema.md`ning `departments.stopped_auto_resume_after_hours`
  qatori.
- Shkurka: `stop_target_list_id` = "Stopda" list.

**Hali qolgan qism** (quyidagi asl reja matnida saqlanadi, endi faqat
ochiq qismlar dolzarb):
- **1.3 — Material turlari shabloni**: hali kiritilmadi, aniq nomlar
  (Laminoks, Eman/dub va h.k.) rahbardan so'ralishi kerak.
- **1.4 — Ikkinchi zavod**: hozircha yo'q, kerak bo'lganda shu hujjatdagi
  1.4-bandga qarab ikkinchi marta yaratiladi.
- **1.5 — Xodimlarni bog'lash**: ATAYLAB qilinmadi —
  `03-fasad-sex-real-ekranlari.md` hal qilinmaguncha faqat ADMIN/SUPERVISOR
  shu bo'limlarga tayinlanishi kerak (boshqa rol 403 ko'radi).

---

**Original reja matni (tarixiy kontekst uchun saqlanadi):**

Barcha kerakli backend tayyor edi (`.claude/plans/09-fasad-sex-modul.md`
Phase 2/3/4), lekin hech kim haqiqiy bosqichlarni kiritmagan edi.

## 1.1. Old shart: Trello board/list'lar

TZ hujjatida (`Nazorat_Trello_Bot_TZ_v1.2_sxemalar_bilan.pdf`, 12-bo'lim)
haqiqiy "nazorat trello" boardi (51 ta list) tahlil qilingan edi. Bu bot
qaysi Trello boardga ulanadi — QAROR KERAK (`05-tz-ochiq-savollar.md`,
savol #9 bilan bog'liq):

- Agar mavjud haqiqiy boarddan foydalanilsa — har bir bosqich uchun
  `trello_list_id`larni o'sha boarddan olish kerak.
- Agar yangi, toza board yaratilsa (`TrelloClient.create_board`, xuddi
  `bot/_seed_demo_data.py` qilgani kabi) — barcha list'lar noldan
  yaratiladi.

⚠️ Ikkalasida ham ish miqdori bir xil — faqat list ID manbai farq qiladi.
Bu qaror kelmaguncha zanjir yaratib bo'lmaydi.

## 1.2. To'liq bosqichlar ro'yxati (TZ 2-bo'lim jadvalidan)

Har biri — bitta `departments` qatori, Mini App'ning "Bo'limlar" →
"Yangi bo'lim qo'shish" formasi orqali (yoki men to'g'ridan-to'g'ri
bajarib beraman):

| # | Bosqich nomi | Maxsus sozlama | Izoh |
|---|---|---|---|
| 1 | Zakaz tushdi | `starts_stopped=True` | "Joy tayyor" kelgunga qadar STOPPED holatda ochiladi |
| 2 | Kontrol | — | 1-2 kishi (`activate_pending_stage`da tanlanadi) |
| 3 | Start | — | Alohida punkt, "Stop"dan keyin ish boshlash |
| 4 | Stolyarka | — | 48/72 soat (qo'lda kiritiladi) |
| 5 | Gip-lab | — | 24 soat |
| 6 | Fayl yig'ish | **fork nuqtasi** (3 target: Korpus/Ichki/Fasad qismi) | `POST /departments/{id}/fork-targets` orqali sozlanadi |
| 7 | Ta'minot | — | 2 holat (shoshilinch/emas) — sotuvchi tanlaydi, tizimga ta'siri yo'q |
| 8 | Laminoks / [Material] fayl tashaldi | — | Har material turi uchun "Yangi material turi" formasi orqali 3talik shablon |
| 9a | Korpus qismi | fork filiali | `previous_task_id` orqali "Fayl yig'ish"ga bog'lanadi |
| 9b | Ichki qism | fork filiali | " |
| 9c | Fasad qismi | fork filiali | " |
| 10 | Korpus sexi (upakovka) | `requires_join=True` | 3 filial ham tugagach avtomatik ochiladi |
| 11 | Sklad | `starts_stopped=True`? | STOP holatida kutadi (aniqlashtirish kerak — 24 soat ichida muammo yo'q bo'lsa avtomatik davom etadimi, yoki qo'lda resume qilinadimi) |
| 12 | Shpon | — | 15 SUTKA (real boarddan tasdiqlangan) |
| 13 | Shkurka | `stop_target_list_id` = "stopda" list | Chiqishda Stop bosilsa alohida list'ga ko'chadi |
| 14 | Kraska | — | 72 soat |
| 15 | Malyarka | — | 15 kun (yumshoq) + ichki 24 soat sub-bosqich (ALOHIDA department sifatida qo'shilishi kerakmi — aniqlashtirish) |
| 16 | Dostavka (Logistika) | — | 24 soat, guruh xabari |
| 17 | Montaj (Ustanovka) | — | Brigada asosida |

Statistika/taymer Kraska-Quritish-O'rash bosqichidan keyin TO'XTAYDI (TZ
11-bo'lim) — Dostavka/Montaj alohida statistika turkumida. Bu — kodga
ta'sir qilmaydi (mavjud tizim allaqachon har bosqichni alohida hisoblaydi),
faqat statistika ko'rsatishda inobatga olinishi kerak bo'lgan izoh.

## 1.3. Material turlari (parallel shablon)

TZ 12.5-bo'limida tasdiqlangan: har material turi (Laminoks, Eman/dub,
va h.k.) uchun bir xil 3 bosqichli shablon. Mini App'da tayyor forma bor
("Yangi material turi") — faqat material nomlarini bilish kerak (kamida
Laminoks va Eman, TZ boshqa turlarni ham eslatgan, aniq ro'yxat rahbardan
so'ralishi kerak).

## 1.4. Ikkinchi zavod (agar kerak bo'lsa)

Agar ikkinchi zavod ham hoziroq ishga tushirilsa — yuqoridagi butun
zanjir **ikkinchi marta**, `factory_name` boshqa qiymat bilan
yaratilishi kerak (masalan `factory_name="zavod_2"`). `module="fasad_sex"`
ikkalasida ham bir xil qoladi — `factory_name` ular orasidagi statistika
ajratuvchi teg.

## 1.5. Xodimlarni bog'lash

Zanjir yaratilgach:
- Har bosqich uchun `trello_list_id` to'ldirilishi kerak (bo'sh bo'lsa
  `create_task()` xato beradi).
- Xodimlar (`employees.department_id`) tegishli bo'limlarga
  tayinlanishi kerak — ⚠️ lekin **buni `03-fasad-sex-real-ekranlari.md`
  hal qilinmaguncha ADMIN/SUPERVISOR'dan boshqa rolga qilmang** — aks
  holda ular Mini App ochganda 403 xatosini ko'radi.

## Kim nima qiladi

Bu bosqich — asosan **ma'lumot/qaror** ishi (qaysi Trello board, qaysi
list ID'lar, xodimlar kimlar). Texnik bajarilishi (formalarni to'ldirish
yoki men API orqali to'g'ridan-to'g'ri yaratib berishim) tez — asosiy
vaqt shu qarorlarni aniqlashtirishga ketadi.
