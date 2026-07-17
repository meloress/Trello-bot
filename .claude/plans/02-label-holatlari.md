# Trello label avtomatikasini TZning 5 holatiga to'ldirish

Holat: ANIQLANGAN BO'SHLIQ — rejalashtirilgan, hali kod yozilmagan.

TZ manbasi: 6.3-band, jadval (5 qator):

| Holat | Qoida |
|---|---|
| ODATIY | Muddatgacha 1 kundan ortiq vaqt bor |
| BUGUNGI ISH | Bugun bajarilishi kerak — to'q sariq (oranjeviy) |
| OGOHLANTIRISH | Muddatga bir sutka qoldi — sariq |
| KECHIKKAN | Muddat o'tib ketgan — QIZIL |
| TO'XTATILGAN | "Stop" bosilgan; sabab kutilmoqda yoki fiksatsiya qilingan |

## Nima bor (2026-07-17 audit natijasi)

`bot/services/trello_sync_service.py`da atigi 3 holat bor:

```python
class CardStatus:
    IN_PROGRESS = "in_progress"   # yashil "Bajarilmoqda"
    DUE_TODAY = "due_today"       # sariq "Bugun tugaydi"
    OVERDUE = "overdue"           # qizil "Muddati o'tgan"
```

`determine_status(deadline, now=None)` faqat `deadline`ga qaraydi —
**`task.status`ni umuman bilmaydi**. Natijada:

- STOPPED vazifa hamon deadline asosidagi rangda ko'rinadi — TO'XTATILGAN
  holati vizual jihatdan Trello'da hech qanday farq qilmaydi (faqat Telegram
  xabarida va bazada bor).
- "BUGUNGI ISH" (to'q sariq, bugun muddati bor) va "OGOHLANTIRISH" (sariq,
  ertaga muddati bor) TZda ikkita alohida holat — kodda bittaga
  (`DUE_TODAY`) birlashtirilgan.

`jobs/daily_sync_job.py:_update_label()` ham faqat `task.deadline`ni
uzatadi, `task.status`ni umuman bermaydi.

## Reja

### 1. `CardStatus` ni 5 holatga kengaytirish

```python
class CardStatus:
    IN_PROGRESS = "in_progress"     # ODATIY — label yo'q/olib tashlanadi
    DUE_TOMORROW = "due_tomorrow"   # OGOHLANTIRISH — sariq (yellow)
    DUE_TODAY = "due_today"         # BUGUNGI ISH — to'q sariq (orange)
    OVERDUE = "overdue"             # KECHIKKAN — qizil (red)
    STOPPED = "stopped"             # TO'XTATILGAN — binafsha (purple)
```

`_LABEL_SPECS`ga mos qatorlar qo'shiladi:
```python
_LABEL_SPECS = {
    CardStatus.DUE_TOMORROW: ("Ogohlantirish", "yellow"),
    CardStatus.DUE_TODAY: ("Bugungi ish", "orange"),
    CardStatus.OVERDUE: ("Muddati o'tgan", "red"),
    CardStatus.STOPPED: ("To'xtatilgan", "purple"),
}
```
`IN_PROGRESS` (ODATIY) uchun TZ maxsus rang belgilamagan ("muddatgacha 1
kundan ortiq bor" — oddiy holat) — mavjud "Bajarilmoqda"/yashil labelni olib
tashlab, hech qanday status-label qo'ymaslik ham TZga mos (ODATIY = maxsus
belgi yo'q). Ikkalasi ham qabul qilinadi, lekin **yashil labelni saqlab
qolish tavsiya etiladi** — Trello'da "hech qanday rang yo'q" holatini "hali
tekshirilmagan"dan farqlab bo'lmaydi, yashil "hammasi joyida" degan aniq
signal beradi.

### 2. `determine_status()` imzosi o'zgaradi — endi `task.status`ni ham oladi

```python
def determine_status(deadline: datetime, task_status: TaskStatus, *, now: datetime | None = None) -> str:
    if task_status == TaskStatus.STOPPED:
        return CardStatus.STOPPED          # eng ustuvor — deadline'dan qat'iy nazar
    now = now or datetime.now(timezone.utc)
    if now > deadline:
        return CardStatus.OVERDUE
    now_date = now.astimezone(TASHKENT_TZ).date()
    deadline_date = deadline.astimezone(TASHKENT_TZ).date()
    if now_date == deadline_date:
        return CardStatus.DUE_TODAY
    if (deadline_date - now_date).days == 1:
        return CardStatus.DUE_TOMORROW
    return CardStatus.IN_PROGRESS
```

STOPPED tekshiruvi ENG BIRINCHI — TZ jadvalida TO'XTATILGAN alohida qator,
deadline holatidan mustaqil ustuvorlikka ega bo'lishi tabiiy (stop bosilgan
vazifa "kechikkan" yoki "ogohlantirish"da bo'lishi ahamiyatsiz, foydalanuvchi
uchun eng muhim signal — bu VAZIFA HOZIR TO'XTAGAN).

### 3. Chaqiruvchi tomon: `jobs/daily_sync_job.py:_update_label()`

```python
async def _update_label(task: Task) -> None:
    status = trello_sync_service.determine_status(task.deadline, task.status)
    await trello_sync_service.update_card_label(task.trello_card_id, status)
```

Boshqa hech narsa o'zgarmaydi — `_list_open_tasks()` allaqachon STOPPED
vazifalarni qamrab oladi (`_OPEN_STATUSES`ga kiradi).

## Tekshirish rejasi

`bot/_smoke_label_states.py`: Test board'da bitta karta, 4 xil holatni
ketma-ket sinab ko'rish (deadline'ni sun'iy o'zgartirib: >1 kun -> ertaga ->
bugun -> o'tgan, keyin STOPPED holatini alohida) — har birida
`GET /cards/{id}?fields=idLabels` orqali kutilgan rang borligini tasdiqlash.

## Tugagach

- `shared/db-schema.md`ga o'zgarish kerak emas (faqat Trello tomonidagi
  label mantiqi, DB ustuni yo'q).
- Ushbu hujjat `.claude/plans/`dan olib tashlanadi, README'dagi qator ham.
