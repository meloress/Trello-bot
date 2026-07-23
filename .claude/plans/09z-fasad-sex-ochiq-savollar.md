# Fasad sex TZ'ning o'z ochiq savollari — kuzatuv ro'yxati

Bu — kod emas, kuzatuv hujjati (`07-tz-ochiq-savollar.md` bilan bir xil
format). Har savol o'z tabiatiga qarab mustaqil yopiladi. TZ §13 (lug'at)
va §14 (12 ta raqamlangan savol) asosida.

| # | Savol | Holat |
|---|---|---|
| 1 | "Municipal" — bu kontekstda nima ma'noni bildiradi? | ❌ HALI HAL QILINMAGAN — hech qanday bosqich/qoidaga bog'lanmagan, kodga hozircha ta'siri yo'q. |
| 2 | "Leyechon"/"yechon qilish" — qaysi bosqichga tegishli amal? | ❌ HALI HAL QILINMAGAN — javob kelgach, agar alohida bosqich bo'lsa, `09-fasad-sex-modul.md` Phase 2'dagi department-create oqimi orqali qo'shiladi (kod o'zgarmaydi). |
| 3 | "Bindoq"/"doq kelyapti" — sifat nazorati (brak) bilan bog'liqmi? | ❌ HALI HAL QILINMAGAN — "ha" bo'lsa, bu YANGI, kattaroq subsystem (nuqson qayd etish), hozirgi tizimda UMUMAN yo'q, shu modul doirasidan tashqari. |
| 4 | "Grubogororya" — atama noaniq. | ❌ HALI HAL QILINMAGAN — imlo/transliteratsiya muammosi bo'lishi mumkin. |
| 5 | "Savina" — brigada/ustaxona nomimi? | ❌ HALI HAL QILINMAGAN — "ha" bo'lsa, Phase 2 (department-create) + mavjud `brigades` jadvali orqali qo'shiladi, kod o'zgarmaydi. |
| 6 | Ustanovkachi/svarshik MISC kategoriya chegarasi (ikkalasi ham bo'lsa-chi)? | ⚠️ BIZNES QARORI — Phase 9'da admin qo'lda tanlaydi, tizim avtomatik aniqlamaydi, kodga bloker emas. |
| 7 | Speed-tier aniq foiz/summalar (1/3/5 kun)? | ❌ HALI HAL QILINMAGAN — Phase 7 mexanizmi tayyor, `speed_tier_schedule` bo'sh default bilan boshlanadi, to'ldirilmaguncha hech narsa taklif qilinmaydi. Javob kelgach kod o'zgarmaydi. |
| 8 | Kontrol: 1 yoki 2 kishi, qachon 2taga o'tiladi? | ⚠️ BIZNES QARORI — Phase 2: kodga bloker emas, har safar operatsion tanlov. |
| 9 | Ikkinchi zavod qaysi shaharda, alohida Trello workspace kerakmi? | ❌ HALI HAL QILINMAGAN — Phase 1's `factory_name` shu sababdan bo'sh matn maydoni. "Alohida workspace" javobi bo'lsa: `TrelloClient` hozir bitta global token/key'ga tayanadi — bo'lim darajasida board/token tanlash logikasi kerak bo'ladi (kattaroq, alohida loyihalash). |
| 10 | Eski CRM arxiv listlari saqlanadimi? | ⚠️ BIZNES QARORI — kodga aloqasi yo'q. |
| 11 | Kunlik hisobot topshirmaslik jarima keltiradimi? | ❌ HALI HAL QILINMAGAN — Phase 8 ataylab faqat kuzatadi. "Ha" bo'lsa: `penalty_service.py`ga yangi funksiya + yangi bracket/skalyar kerak bo'ladi, mavjud `apply_penalty_for_employees()` yadrosi qayta ishlatiladi. |
| 12 | Kunlik norma "actual" qiymati qanday o'lchanadi (sqm maydoni yo'q)? | ❌ HALI HAL QILINMAGAN — Phase 6 hozircha yakunlangan-vazifa-soni proksi ishlatadi. Haqiqiy sqm kerak bo'lsa: `tasks.sqm_completed: FLOAT NULL` + finish-oqimiga yangi input maydoni kerak bo'ladi. |
| 13 | Fork paytida Trello karta qaysi list'da qoladi? | ⚠️ ARXITEKTURA TAYYOR, TASDIQ KERAK — reja fork-nuqtasida qoldirishni tavsiya qiladi, foydalanuvchi bilan bitta savol sifatida tasdiqlanishi kifoya. |
| 14 | Ustanovkachi/svarshik uchun "vazifa buyurish" toifalarining aniq Uzbek nomlari? | ⚠️ BIZNES QARORI — Phase 9 enum qiymatlari yakuniy nomlanishdan oldin joy egallovchi (placeholder) sifatida yoziladi. |

## Amaliy xulosa

17 savoldan (13 raqamlangan + 4 lug'at atamasi jamlanib 14 qatorga
tushirilgan) 4 tasi ⚠️ BIZNES QARORI (koddan mustaqil, operatsion), 10 tasi
❌ HALI HAL QILINMAGAN (kod hozircha shu javoblarsiz ham ishlaydi — default
bilan yoki mexanizm tayyor-lekin-inert holatda), 3 tasi (5, 9, 13 qisman)
arxitektura tayyor-faqat-tasdiq-kerak toifasida. Hech biri Phase 0-9'ning
boshlanishiga TO'SQINLIK qilmaydi — barchasi kelajakda javob kelganda mos
kod joyiga (yuqorida ko'rsatilgan) qo'shiladi.

## Tugagach

Barcha qatorlar ✅ bo'lgach, bu hujjat papkadan olib tashlanadi (git
tarixida saqlanib qoladi), README'dagi qator ham.
