# SPEC.md ni Nazorat Trello (`fasad_sex`) uchun amalga oshirish — dizayn

Sana: 2026-07-31 · Manba: `SPEC.md` · Modul: `departments.module == "fasad_sex"`

## Kontekst

`SPEC.md` — butun tizim uchun TZ. Kod bazasi bu talablarning katta qismini
allaqachon qoplaydi (17-bosqichli zanjir, fork/join, STOP + StopLog +
sotuvchiga xabar, `penalty_rules`, MISC vazifalar + kategoriyalar, Mini App
admin paneli). Bu hujjat faqat **farqni** — SPEC talab qilgan, lekin kodda
yo'q narsalarni — qamraydi.

### Qattiq cheklov: mebel muzlatilgan

`timer_service`, `penalty_service`, `overdue_watch_job`, `stats_service` —
ikkala modul uchun umumiy dvigatel. Har bir o'zgarish `fasad_sex` tomonida
guard bilan qilinadi; mebelning bugungi xatti-harakati **bir bit ham
o'zgarmaydi**. Amaliy qoida: yangi ustunlar `NULL`/`False` standart bilan
qo'shiladi va `NULL` = "bugungi xatti-harakat".

### Yopilgan qarorlar

- **§13 #5 — soat hisobi: kalendar (24/7).** Ish smenasi, dam olish kuni
  hisobga olinmaydi. Hozirgi kod ham shunday ishlaydi, ya'ni o'zgarish yo'q.
- **§13 #2** — kunlik norma (5 punkt) `drawing` bosqichiga tegishli:
  SPEC §5.2 ning o'zi shunday deydi.
- **§13 #3** — "ikkalasigami yoki bittasigami" → SPEC §7 "sozlanadigan
  bo'lsin" deydi; standart = ikkalasiga (bugungi xatti-harakat).
- **§13 #1, #7** — shu repoda allaqachon yopilgan
  (`.claude/nazorat-trello/05-tz-ochiq-savollar.md`).
- **§13 #6, #8** — ma'lumot/SaaS masalasi, kodni bloklamaydi.

### Qamrovdan tashqari

- §3 `Company` (multi-tenant) va §10 tarif rejasi — SaaS reja bekor
  qilingan, `factory_name` bilan aralashtirilmaydi.
- §7 tezlik bonusi (1/3/5 sutka tarif) — 8.6-band sifatida 2026-07-27 da
  ataylab o'chirilgan. Qayta tiklash alohida so'rov.
- §3 `NotificationLog` — hech bir talab unga tayanmaydi, YAGNI.

---

## Faza 1 — SLA dvigateli (§5.1, §6.1, §5.4)

Eng muhim bo'lak: hozir har bosqich `PENDING_SETUP` bilan ochilib, muddatni
odam qo'lda kiritadi. SPEC §5.1 esa muddat bosqichga **kirgan vaqtdan**
avtomatik hisoblanishini talab qiladi.

### 1.1 Bo'limga standart SLA

`departments.default_sla_hours: int | None` (NULL = SLA yo'q).

`advance_task_stage()` yangi bosqich yaratganda, `fasad_sex` va
`default_sla_hours` bo'lsa — `deadline = now + sla` **oldindan to'ldiriladi**.
Bosqich baribir `PENDING_SETUP` bo'lib qoladi (xodim hali tayinlanmagan), lekin
soat allaqachon to'g'ri ishlaydi.

Nega `PENDING_SETUP` saqlanadi: `PENDING_SETUP` ikki narsani kutadi —
muddat **va** xodim. SLA faqat birinchisini yechadi. Muhim yutuq: soat
nazoratchi tugma bosgan vaqtdan emas, buyurtma bosqichga kirgan vaqtdan
ketadi — §5.1 aynan shuni talab qiladi.

`activate_pending_stage()` — `deadline` argumenti ixtiyoriy bo'ladi;
berilmasa oldindan to'ldirilgani saqlanadi (nazoratchi baribir qo'lda
o'zgartira oladi).

### 1.2 STOP taymerni muzlatadi (§6.1)

Hozir STOP `deadline` ga umuman tegmaydi — ishchi to'xtatilgan vaqt uchun
ham jarima oladi. SPEC: `due_at` STOP davomiyligiga suriladi.

- `tasks.stopped_seconds_total: int` (default 0).
- `resume_task()` — `fasad_sex` bo'lsa: `paused = resumed_at - stopped_at`,
  `deadline += paused`, `stopped_seconds_total += paused`.
- `stopped_seconds_total` statistikada ham ishlatiladi (§6 "STOP vaqti ish
  vaqtidan chiqarib tashlanadi") — Faza 4.
- Mebel: guard tufayli tegilmaydi.

### 1.3 Sozlanadigan eslatmalar (§5.4)

`app_settings` ga ikkita skalyar:

| Maydon | Default | Ma'nosi |
|---|---|---|
| `deadline_warning_hours` | 4 | Muddat tugashiga shuncha soat qolganda ogohlantirish |
| `overdue_repeat_hours` | 12 | Kechikish davom etsa, har shuncha soatda takroriy xabar |

- `list_deadline_approaching(within_hours=...)` endi kodga tikilgan 24 emas,
  shu sozlamani oladi.
- `tasks.last_overdue_reminder_at` — takroriy eslatma uchun.
  `overdue_watch_job` ga to'rtinchi mustaqil faza: OVERDUE holatdagi
  `fasad_sex` vazifalar, oxirgi eslatmadan `overdue_repeat_hours` o'tgan
  bo'lsa — qayta xabar.

### 1.4 Tekshiruv

`bot/tests/test_sla_engine.py` — repolar soxta, DB yo'q (mavjud
`test_penalty_responsible.py` shakli): SLA hisobi, STOP siljishi
(mebel uchun siljimasligi ham), eslatma oynasi.

---

## Faza 2 — Maxsus SLA qoidalari (§5.2, §5.3)

### 2.1 Chizish navbat qoidasi

`tasks.is_urgent: bool` (default False) + bo'lim darajasidagi konfiguratsiya:

| Maydon | Ma'nosi |
|---|---|
| `daily_quota` | Kuniga necha zakaz "normada" |
| `sla_urgent` | Srochniy zakaz uchun soat (24) |
| `sla_within_quota` | Normadagi (birinchi N ta) uchun (48) |
| `sla_over_quota` | Normadan oshganlar uchun (72) |

To'rttasi ham bo'lim qatorida `NULL` bo'lsa — §1.1 dagi oddiy
`default_sla_hours` ishlaydi. Kunlik tartib = shu bo'limda shu kalendar
kunda (Toshkent) yaratilgan bosqichlar soni.

### 2.2 Blok SLA (§5.3)

`departments.sla_block_id: str | None` — bir xil qiymatga ega ketma-ket
bo'limlar bitta blok (shkurka + kraska + malyarka). Blok ichidagi bosqichlar
o'z muddatini olmaydi; muddat **blokka kirgan** paytda qo'yiladi va blokdan
chiqquncha o'zgarmaydi (15 kun). Blok ichidagi o'tishlarda `deadline`
ko'chiriladi, jarima esa faqat blokdan chiqishda hisoblanadi.

---

## Faza 3 — Xabarnoma va rollar (§7, §8)

- `departments.telegram_chat_id: str | None` — sex guruhi. §8 jadvalidagi
  uchta hodisa (yangi vazifa, muddat o'tdi, bosqichga o'tdi) guruhga ham
  ketadi. NULL = guruh yo'q, hech narsa yuborilmaydi.
- `employees.manager_id: int | None` (self-FK) — §7/§8 "rahbar ham
  xabarnomaga ulanadi". `notify_task_overdue` va `notify_penalty_applied`
  qabul qiluvchilar ro'yxatiga qo'shiladi.
- `app_settings.penalize_all_assignees: bool` (default True) — §7
  "ikkalasigami yoki faqat asosiy mas'ulgami". False bo'lsa
  `_write_scores_for_employees()` faqat birinchi javobgarga yozadi.

## Faza 4 — Dashboard (§11)

`stats_service` ga to'rt yangi funksiya + Mini App ekranlari:

- **Voronka** — bo'lim bo'yicha ochiq vazifalar soni.
- **Bottleneck** — bosqichning o'rtacha haqiqiy davomiyligi vs
  `default_sla_hours` (STOP vaqti chiqarilgan holda,
  `stopped_seconds_total` orqali).
- **STOP statistikasi** — nechta vazifa, jami qancha vaqt, sabablar kesimi.
- **Eksport** — CSV (Excel o'qiydi), yangi bog'liqlik qo'shilmaydi.

---

## Migratsiyalar

Har faza bitta migratsiya. Barcha yangi ustunlar `nullable=True` yoki
`server_default` bilan (jadvallar bo'sh emas). Yakunda
`shared/db-schema.md` yangilanadi.

---

## Bajarilish holati (2026-08-01)

To'rt fazaning hammasi amalga oshirildi va `main`ga tayyor
(`spec-nazorat-trello` branchi, 4 commit):

| Faza | Commit | Migratsiya |
|---|---|---|
| 1 — SLA dvigateli (§5.1/§6.1/§5.4) | `0967ec4` | `c7f2a91b0d48` |
| 2 — navbat + blok SLA (§5.2/§5.3) | `f3d13fa` | `d5b83e10c9a7` |
| 3 — guruh/rahbar/jarima maqsadi (§7/§8) | `1f0478f` | `e9c04a7f3b62` |
| 4 — dashboard (§11) | `ab824ab` | — (jadval qo'shilmagan) |

Uchala migratsiya production DB'ga qo'llangan (`alembic current` =
`e9c04a7f3b62`). Barcha 6 test o'tadi; `test_sla_engine.py` yangi, uchta
tuzatish sabotaj bilan tekshirilgan (ataylab buzilganda yiqiladi).

**Rejadan chetlanish:** Faza 2 da "norma ichida" uchun alohida
`sla_within_quota` ustuni qo'shilmadi — `default_sla_hours`ning o'zi shu
rolni bajaradi, ya'ni navbat qoidasi o'chirilganda xatti-harakat avtomatik
oddiy SLA'ga qaytadi (bitta ustun kam, bitta nomuvofiqlik holati kam).

**Haqiqiy DB ustidagi tekshiruv topgan xato:** `get_stop_stats()` davom
etayotgan STOP'ni kelajakdagi `until`gacha hisoblardi — joriy oy filtrida
6 soatlik to'xtatishni 30 soat qilib ko'rsatgan edi. `min(until, now)`
bilan tuzatildi.

**Qolgan ish (kod emas):** yangi ustunlarning hech biri hali to'ldirilmagan
(hammasi NULL) — 17 ta `fasad_sex` bo'limi uchun SLA soatlari, chizish
bosqichining normasi, "paint" blokining a'zolari va sex guruh ID'lari
rahbardan olinishi kerak. Shu qiymatlar kiritilmaguncha tizim aynan
bugungidek ishlaydi.
