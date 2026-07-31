# 1. Haqiqiy Fasad sex zanjiri — qolgan ishlar

Asosiy zanjir (17 department, `module="fasad_sex"`, yangi Trello board,
to'liq chiziqli/fork/join bog'lanish) DB'da allaqachon yaratilgan va
tekshirilgan (bajarilgan ish tarixi git logda). Real DB tekshiruvida
tasdiqlandi: barcha 17 bo'limda `trello_list_id` bor, fork (`Fayl
yig'ish`→3 filial) va join (`Korpus sexi`) to'g'ri bog'langan. Qolgan
qism — faqat quyidagilar:

## 1.3. Material turlari (parallel shablon) — ✅ BAJARILDI (2026-07-31)

TZ 12.5-bo'limida tasdiqlangan: har material turi (Laminoks, Eman/dub,
va h.k.) uchun bir xil 3 bosqichli shablon. Rahbar tasdiqladi: hozircha
**Laminoks va Eman/dub** bilan boshlash (to'liq ro'yxat keyinroq
qo'shiladi). DB'ga to'g'ridan-to'g'ri yaratildi (`module="fasad_sex"` —
Mini App'ning `screenAddMaterialTemplate` formasi orqali EMAS, chunki
o'sha forma `POST /admin/departments`ni `module`siz chaqiradi va
natijada yangi bo'lim sukut bo'yicha `module="mebel"`ga tushib qolar
edi — bu shu jarayonda topilgan haqiqiy nuqson, hali tuzatilmagan, ниже
"Texnik qarz"ga qarang):
- **Laminoks**: fayl tashaldi (id 94) → ishlab chiqarishda tasdiqlandi
  (id 95) → 100% tayyor (id 96)
- **Eman/dub**: fayl tashaldi (id 97) → ishlab chiqarishda tasdiqlandi
  (id 98) → 100% tayyor (id 99)

Trello list bog'lanmagan (`trello_list_id=NULL`) — asl `screenAddMaterialTemplate`
formasi ham buni so'ramaydi, shuning uchun ataylab shunday qoldirildi.

## 1.4. Ikkinchi zavod (agar kerak bo'lsa) — qaror qayd etildi, yaratish keyinga qoldirildi

Rahbar javobi (2026-07-31): **ikkala zavod ham Toshkent shahrida, bitta
Trello workspace ichida** bo'ladi — `05-tz-ochiq-savollar.md` savol #1
shu bilan hal bo'ldi (alohida Trello workspace kerak emas).

Lekin zanjirni **hoziroq ikkinchi marta** (`factory_name="zavod_2"`)
yaratish so'ralmadi — 1-zavod hali amalda ishlamayotgan ekan (1.5-band
hali ochiq), ikkinchisini oldindan yaratish YAGNI bo'lardi. 1-zavod
to'liq ishga tushgach, shu qarorga asosan bir buyruq bilan yaratiladi.

## 1.5. Xodimlarni bog'lash — ENG MUHIM OCHIQ BAND (davom etmoqda)

Real DB tekshiruvida tasdiqlandi: 17 ta `fasad_sex` bo'limining **hech
birida faol xodim yo'q** (0 xodim), va shu bo'limlarda **birorta ham
task yaratilmagan** — ya'ni zanjir texnik jihatdan tayyor, lekin modul
hali amalda ishlatilmagan. Hozirgi 12 faol xodim (2 brigadir + 10
ishchi) barchasi allaqachon `mebel` bo'limlariga (38/39/40) tayinlangan
— fasad_sex uchun bo'sh xodim yo'q, demak bu **yangi ro'yxatdan
o'tkaziladigan yoki mebel'dan ko'chiriladigan** xodimlar bo'lishi kerak.

**2026-07-31 progress:**
- DB'da 17 bo'lim hozircha **haqiqiy, bo'sh "Fasad sex — Ishlab
  chiqarish" boardga** ulangan holicha qoldi (`trello_list_id`lar
  o'zgarmagan) — bu board 0 karta bilan, sinov uchun xavfsiz.
- Rahbar ko'rsatgan **haqiqiy, jonli** "nazorat trello" board
  (`https://trello.com/b/fOC82usT/nazorat-trello`, 51 ochiq list, 4029
  ochiq karta, real mijoz ma'lumotlari — 2018-yildan buyon ishlatilib
  kelinmoqda) topildi va tegilmadi. Uning **struktura nusxasi**
  (faqat 51 list nomi/tartibi, kartasiz) "Nazorat Trello demo"
  (`https://trello.com/b/Y3eXUO8Q/nazorat-trello-demo`) nomi bilan
  yaratildi.
- **Ochiq**: "nazorat trello"dagi 51 nomariy list DB'dagi 17 formal
  bo'lim nomiga to'g'ridan-to'g'ri mos kelmaydi (masalan "Montaj
  (Ustanovka)" o'rniga alohida brigada listlari — Odil ustanovka,
  Abdulaziz brigada, Bahodir omil-brigadasi, Olim brigada, Xasan aka
  Brigada, Mirodilla ustanovka, Aziz ustanovka bor). Rahbar bu
  moslashtirishni o'zi berishga rozi bo'ldi — hali kelmagan. Ro'yxat
  kelgach: 17 bo'limning `trello_list_id`si demo boarddagi mos
  listlarga ulanadi (sinov uchun), keyin xuddi shu moslashtirish bilan
  haqiqiy "nazorat trello" boardga ulanadi ("tugagach haqiqiysini
  ulaymiz" bosqichi).
- Xodimlar (`employees.department_id`) tegishli `fasad_sex` bo'limlarga
  tayinlanishi kerak (Mini App'ning xodim tahrirlash ekrani orqali) —
  buning uchun kamida bitta real xodim botga `/start` orqali ro'yxatdan
  o'tishi kerak (bu bot orqali qilib bo'lmaydi, foydalanuvchi/hamkasb
  Telegram'da o'zi bajarishi kerak).
- Shundan keyingina zanjir haqiqiy tsiklda (`6.2` — to'liq E2E test,
  rahbar Mini App orqali o'zi sinaydi) sinaladi.

## Kim nima qiladi

Bu bosqich — asosan **ma'lumot/qaror** ishi (material nomlari, ikkinchi
zavod kerakmi, kimlar qaysi bo'limga tayinlanadi). Texnik bajarilishi
(Mini App orqali yoki men API orqali to'g'ridan-to'g'ri) tez.
