# Trello + Telegram Bot — Talablar auditi (TZ checklist)

> Manba: loyiha menejeri bilan suhbat transkripti (22.07.2026).
> Audit sanasi: **04.08.2026**. Tekshirilgan modul: `fasad_sex` ("Nazorat Trello").
> Belgilar: ✅ BOR / ⚠️ QISMAN / ❌ YO'Q
>
> **Natija: 41 banddan — ✅ 29 · ⚠️ 8 · ❌ 4**

---

## 1. Umumiy arxitektura — ✅4 ⚠️1

- [x] ✅ **1.1** Zakaz = Trello kartasi — `bot/services/task_service.py:185` (`create_task`), karta yaratish DB yozuvidan oldin.
- [x] ✅ **1.2** Bosqichlar qattiq kodlanmagan — `departments` jadvali, `next_department_id` zanjiri. Qo'shish/o'chirish: `POST/DELETE /admin/departments` (`bot/miniapp/api/admin.py:130,187`).
- [x] ✅ **1.3** Har bosqichga xodim + muddat + jarima: `task_assignments`, `departments.default_sla_hours`, `penalty_rules` (bo'lim bo'yicha ham, umumiy ham).
- [ ] ⚠️ **1.4** Ko'p odam biriktirish — **dvijok qo'llab-quvvatlaydi** (`task_assignments` N ta qator, `delegate_task` ro'yxat oladi), lekin **admin UI bosqichga faqat 1 brigadir qo'yadi** (`admin.py:466` — `employee_ids=[brigadier_id]`). Ko'p odam faqat brigadir ichkarida bo'lganda paydo bo'ladi. Kontrol zam / chizishga admin darhol 2 odam qo'ya olmaydi.
- [x] ✅ **1.5** Sex tanlash — `POST /admin/tasks` `department_id` majburiy (`admin.py:424`).

## 2. Muddat (srok) mantiqi — ✅5 ⚠️1 ❌1

- [x] ✅ **2.1** Sanash bosqichga **kirgan paytdan** — `task_service.resolve_stage_deadline():421`, `_spawn_pending_stage():437`da chaqiriladi. Ya'ni nazoratchi tugma bosgan paytdan emas.
- [x] ✅ **2.2** `started_at` — to'liq sana/vaqt, SLA esa **soatda** (`default_sla_hours`).
- [ ] ❌ **2.3** Muddatni **qo'lda o'zgartirish yo'q**. Muddat faqat 2 joyda qo'yiladi: yaratishda (`admin.py:437`) va `PENDING_SETUP`ni faollashtirishda (`admin.py:1190`). ACTIVE/OVERDUE bosqichning muddatini surish uchun endpoint ham, ekran ham yo'q. `timer_service.reopen_if_overdue():280` bor, lekin unga UI ulanmagan.
- [x] ✅ **2.4** Muddat o'tsa — `jobs/overdue_watch_job.py:51` OVERDUE qiladi, `penalty_service.calculate_and_apply_task_penalty():266` minus ball yozadi.
- [x] ✅ **2.5** Jarima aynan o'sha bosqichning odamiga — `_write_scores_for_employees():86` (ishchi bo'lsa ishchiga + brigadirga ulush; ishchi yo'q bo'lsa brigadirga to'liq).
- [ ] ⚠️ **2.6** "Srochniy" — `tasks.is_urgent` bor va 24 soat beradi, lekin **ikki cheklov bilan**: (a) faqat **buyurtma yaratilayotganda** belgilanadi, keyin yoqib/o'chirib bo'lmaydi; (b) faqat `sla_urgent_hours` sozlangan bo'limda ishlaydi — bazada bu **faqat "Start" (chizish)** bo'limida. Qolgan 22 bo'limda srochniy muddatga ta'sir qilmaydi.
- [x] ✅ **2.7** Standart muddatlar admin paneldan — `POST /admin/departments/{id}` `default_sla_hours`, `sla_urgent_hours`, `daily_quota_orders`, `sla_over_quota_hours`, `sla_block_id` (`admin.py:232`).

## 3. STOP funksiyasi — ✅6 (to'liq)

- [x] ✅ **3.1** Istalgan bosqichda STOP — `timer_service.stop_task():127` (ACTIVE va OVERDUE holatida ham).
- [x] ✅ **3.2** Taymer **muzlaydi** — `resume_task():190` to'xtab turgan davrni `deadline`ga qo'shadi va `tasks.stopped_seconds_total`ga yozadi. STOPDA turgan vazifa OVERDUE bo'lmaydi.
- [x] ✅ **3.3** Vizual belgi — `_sync_stop_label():56`, Trello'da to'q sariq "To'xtatilgan" label; Resume'da muddatga mos rang qaytadi. Bundan tashqari `stop_target_list_id` sozlangan bo'lsa karta "stopda" ro'yxatiga ko'chadi.
- [x] ✅ **3.4** Sotuvchiga xabar — `task_sellers` jadvali (buyurtmaga 3 tagacha sotuvchi), `notification_service.notify_task_stopped():185` ularning hammasiga yuboradi.
- [x] ✅ **3.5** "Stop bosilgan zakazlar" ro'yxati — `GET /admin/stopped-orders` (`admin.py:869`) + `stats_service.get_stopped_orders():412`.
- [x] ✅ **3.6** STOP vaqti statistikada alohida — `stats_service.get_stop_stats():548` (soni, umumiy soat, sabablari) va bajarilish vaqtidan chegiriladi.

## 4. Jarayon bosqichlari — ⚠️ (bazadagi 23 bo'lim TZ jadvaliga to'liq mos emas)

Bazadagi haqiqiy zanjir (04.08.2026):
`Zakaz tushdi(STOP) → Kontrol 24 → Start 48/24/72 → Stolyarka 24 → Gip-lab 24 → Fayl yig'ish 24 → [FORK: Korpus qismi 24 | Ichki qism 24 | Fasad qismi 72] → Korpus sexi (upakovka) 24 [JOIN] → Sklad 24 (STOP) → Shpon 360 → Shkurka 72 → Kraska 72 → Malyarka 24 → Dostavka 24 → Montaj 48`

| TZ bandi | Holat | Izoh |
|---|---|---|
| 1 Zakaz tushdi | ✅ | `starts_stopped=True` — boshida STOPda turadi |
| 2 Kontrol zam 24 | ✅ | "Kontrol", 24 soat |
| 3 Chizish 48/72/24 | ✅ | "Start": 48 standart, 24 srochniy, kuniga 5 punktdan oshsa 72 — TZ normasi aynan bajarilgan |
| 4 Gip-lab 24 | ✅ | "Gip-lab", 24 |
| 5 Fayl yig'ish 24 | ✅ | "Fayl yig'ish", 24 |
| 6 Fayl + zapchast 24 | ⚠️ | Alohida bosqich yo'q; "Stolyarka" bor, lekin bu boshqa narsa |
| 7 Ta'minot (muddatsiz) | ❌ | Bunday bo'lim umuman yo'q |
| 8 Fayl tashlash 24 | ⚠️ | "Laminoks fayl tashaldi" 24 va "Eman/dub fayl tashaldi" 24 bor, **lekin asosiy zanjirga ulanmagan** (hech bir bo'lim ularga `next` bermaydi) |
| 9 Laminat zavodi 72 | ⚠️ | "…ishlab chiqarishda tasdiqlandi" 72 — yuqoridagi kabi zanjirdan uzilgan. 2 zavod (Laminoks, Eman/dub) shabloni bor |
| 10 Raspil (ajralish) | ⚠️ | Ajralish bor, lekin "Fayl yig'ish"da va 3 tarmoqqa (Korpus/Ichki/Fasad), "Raspil" nomli bosqich yo'q |
| 11 Korpus sex 24 | ✅ | "Korpus sexi (upakovka)", 24, join nuqtasi |
| 12 Fasad 15 sutka umumiy | ⚠️ | Shpon 360 soat (=15 sutka) + Shkurka 72 + Kraska 72 — **har biriga alohida**, umumiy blok emas. `sla_block_id` bo'sh (ataylab: doskadagi soatlar blokni bekor qildi) |
| 13 Malyarka/quritish/upakovka | ⚠️ | "Malyarka" 24 bor; quritish alohida yo'q, upakovka Korpus sexiga qo'shib yuborilgan |
| 14 Dostavka 24 | ✅ | 24 soat. Lekin logistika **guruhiga** xabar yo'q (5.4ga qarang) |
| 15 Dostavkadan keyin STOP | ❌ | Montajda `starts_stopped=False` — avtomatik STOP bo'lmaydi |
| 16 Ustanovka | ⚠️ | Bitta "Montaj (Ustanovka)" 48 soat. 7–8 brigada ajratilmagan (bazada umuman 3 brigada bor, ular mebelniki) |

- [ ] ⚠️ **4.1** Bosqichlar qisman: 16 tadan **9 tasi to'liq**, 5 tasi qisman, 2 tasi yo'q.
- [x] ✅ **4.2** Ajralish va qayta birlashish — `department_fork_targets` + `departments.requires_join`, `advance_task_stage():483`. Bazada tirik: 78→(79,80,81)→82. *Ma'lum kamchilik: ikki tarmoq bir vaqtda tugasa join ikki marta ochilishi mumkin (race).*
- [x] ✅ **4.3** "Necha sutkada bajarildi" — `stats_service.get_stage_bottlenecks():494` (bosqich bo'yicha o'rtacha, STOP vaqti chegirilgan) + `get_order_funnel():450`.

## 5. Xabarnomalar — ✅2 ⚠️3 ❌1

- [x] ✅ **5.1** Xodimga shaxsiy xabar — `notify_task_started():123` (Mini App tugmasi bilan).
- [ ] ⚠️ **5.2** Rahbarga dublikat — **kod bor** (`employees.manager_id`, `_add_managers():84`), lekin bazada **15 xodimdan 0 tasiga rahbar biriktirilgan**. Ma'lumot kiritilmaguncha ishlamaydi.
- [ ] ⚠️ **5.3** Sotuvchiga — **STOP bo'yicha ✅** (3.4), lekin "zakaz harakati" (bosqich o'tishi) bo'yicha sotuvchiga xabar yo'q; bosqich o'tishi faqat **mijozga** ketadi (`notify_client_stage_advanced():475`).
- [ ] ⚠️ **5.4** Guruhga xabar — **kod bor** (`departments.telegram_chat_id`, `_department_chat_id():71`), lekin **23 bo'limdan hech birida guruh ID kiritilmagan**. Bot avval har bir guruhga qo'shilishi kerak.
- [x] ✅ **5.5** Muddat eslatmalari — `overdue_watch_job.py:29` (tugashiga N soat qolganda, `deadline_warning_hours`=4), `:51` (o'tganda), `:70` (har 12 soatda takroriy).
- [ ] ❌ **5.6** O'chirib bo'lmaydigan xabar — **texnik jihatdan imkonsiz**: Telegram foydalanuvchisi istalgan botni "mute"/"block" qila oladi, buni bot tomondan bloklab bo'lmaydi. Yagona haqiqiy chora — o'qilmagan xabarni statistikaga chiqarish/rahbarga eskalatsiya (hozir eskalatsiya faqat kechikish bo'yicha bor).

## 6. "Vazifa buyurish" moduli — ✅4 ⚠️1

- [ ] ⚠️ **6.1** Jarayon boshida alohida "punkt" sifatida **yo'q** — MISC vazifalar buyurtma zanjiridan mustaqil, alohida tur (`tasks.task_type=misc`). Amalda ishlaydi, lekin zanjirdagi bosqich emas.
- [x] ✅ **6.2** Uch xil tur — `MiscCategory`: `office`, `fasad_sex`, `installer`, `welder` (TZdagi 3 turni qoplaydi, ustanovkachi/svarshik alohida).
- [x] ✅ **6.3** Rahbar vazifa berib muddat qo'yadi — `POST /admin/misctasks` (`admin.py:693`).
- [x] ✅ **6.4** "Mening vazifalarim" — `GET /misctasks` (`worker.py:90`), Mini Appda alohida tab.
- [x] ✅ **6.5** MISC uchun ham ball/jarima — `worker.py:242` bir xil `calculate_and_apply_task_penalty` yo'lidan o'tadi.

## 7. Statistika va dashboard — ✅4 ⚠️1

- [x] ✅ **7.1** Xodim kesimi — `get_monthly_stats():186` (bajarilgan, ball, jarima soni, o'rtacha vaqt) + kunlik/haftalik.
- [ ] ⚠️ **7.2** Sex kesimi — **qisman**: bo'lim bo'yicha bo'g'iz/o'tkazuvchanlik bor (`get_stage_bottlenecks`, `get_capacity_vs_actual`, `get_order_funnel`), lekin "sex bo'yicha jami ball/jarima" jadvali yo'q — statistika ekrani **rol** bo'yicha guruhlanadi, bo'lim bo'yicha emas.
- [x] ✅ **7.3** Brigada hisobi — `get_brigade_monthly_stats():239` + brigadir ekrani.
- [x] ✅ **7.4** STOP chegirilgan sof vaqt — `_compute_stats():121` (`finished_at - started_at - stopped_seconds_total`), bo'g'iz hisobida ham.
- [x] ✅ **7.5** Rahbar dashboardi — `GET /admin/dashboard` (`admin.py:77`) + alohida web panel (`web/`), CSV eksport (`admin.py:951`).

## 8. Sozlanuvchanlik / sotuvga tayyorlik — ✅2 ❌2

- [x] ✅ **8.1** Gibkiylik — bosqich/muddat/bo'lim hammasi bazadan, admin roli orqali Mini Appdan o'zgaradi. Jarima jadvali (`penalty_rules`) ham ma'lumot, kod emas.
- [x] ✅ **8.2** Yangi bosqich qo'shish — `POST /admin/departments` + `/chain` + `/fork-targets` (`admin.py:130,279,322`).
- [ ] ❌ **8.3** Multi-tenant (har korxona/shourum alohida) — **yo'q va ataylab qilinmagan** (SaaS rejasi bekor qilingan). Hozir bor narsa: `departments.module` (2 ta ishlab chiqarish liniyasi) va `factory_name` (zavod bo'yicha statistika) — bu multi-tenant emas, bitta korxona ichidagi bo'linish.
- [ ] ❌ **8.4** Tarif rejalari (sodda/to'liq) — yo'q, kodda tarif tushunchasi umuman mavjud emas.

---

## Muhimlik bo'yicha yetishmayotgan ishlar

**A. Bloklovchi — ma'lumot kiritish kerak, kod tayyor** *(bir necha soatlik ish, dasturlash emas)*
1. **5.4** Har bir sexning Telegram guruh ID'sini kiritish (bot avval guruhga qo'shiladi). 23 bo'limdan 0 tasi sozlangan.
2. **5.2** Xodimlarga rahbar (`manager_id`) biriktirish — 15 xodimdan 0 tasida bor.
3. **1.5/4.16** Ustanovka brigadalari (7–8 ta) va sexlarga haqiqiy xodimlarni taqsimlash — hozir `fasad_sex`da 0 vazifa, brigadalar yo'q.

**B. Muhim — kod yozish kerak**
4. **2.3 Muddatni qo'lda o'zgartirish** — eng ko'p og'riq beradigan kamchilik: ishlab turgan bosqichning muddatini surib bo'lmaydi. Kerak: `POST /admin/tasks/{id}/deadline` + Mini Appda tugma. *(kichik ish, ~yarim kun)*
5. **2.6 Srochniy belgisini keyin qo'yish** va uni barcha bo'limlarga ta'sir qildirish (hozir faqat "Start"da). Kerak: `is_urgent` toggle endpoint + bo'limlarga `sla_urgent_hours` kiritish.
6. **4.15 Dostavkadan keyin avtomatik STOP** — bir ustunni yoqish: Montaj bo'limiga `starts_stopped=True`.
7. **4.7/4.8/4.9 Ta'minot bosqichi** va **laminat zavodi zanjirini asosiy oqimga ulash** — hozir "Laminoks"/"Eman-dub" shablonlari osilib qolgan, hech qayerdan kirilmaydi. Biznes qarori kerak: bu bosqichlar zanjirning qaysi joyiga ulanadi?
8. **1.4 Bir bosqichga 2+ odam** — admin darhol 2 kishi qo'ya olishi (kontrol zam, chizish). Dvijok tayyor, faqat UI + endpoint ro'yxat qabul qilishi kerak.

**C. Yaxshilash**
9. **5.3** Sotuvchiga bosqich o'tishi bo'yicha ham xabar (hozir faqat STOP).
10. **7.2** Statistikada sex bo'yicha guruhlash (hozir faqat rol bo'yicha).
11. **4.12** Fasad yo'nalishiga 15 sutkalik **umumiy** blok qo'yish (`sla_block_id`) — hozir har bosqich alohida sanaydi. Bu doskadagi soatlar bilan ziddiyatli, biznes qarori kerak.
12. **4.2** Fork/join poygasi (ikki tarmoq bir vaqtda tugaganda join ikki marta ochilishi) — hozir zarar yo'q, chunki oqim hali ishlamayapti.

**D. Qilinmaydi (ataylab)**
- **8.3 multi-tenant**, **8.4 tarif** — SaaS rejasi bekor qilingan. Qayta kerak bo'lsa alohida loyiha.
- **5.6 o'chirib bo'lmaydigan xabar** — Telegram buni ruxsat bermaydi.
