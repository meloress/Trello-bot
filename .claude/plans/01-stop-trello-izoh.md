# "Stop" bosilganda Trello kartasiga izoh yozish

Holat: ANIQLANGAN BO'SHLIQ — rejalashtirilgan, hali kod yozilmagan.

TZ manbasi: 7.5-band, aniq matn: *"Stop holati Trello kartasiga izoh bo'lib
yoziladi: vaqt, kim to'xtatgani, sabab."* Bu ochiq savol emas — TZning qat'iy
talabi.

## Nima yo'q (2026-07-17 audit natijasi)

- `bot/trello/client.py`da kartaga izoh (comment) qo'shadigan metod UMUMAN
  yo'q.
- `bot/services/timer_service.py:stop_task()` faqat `stop_logs` jadvaliga
  yozadi, Trello'ga umuman murojaat qilmaydi.
- `bot/handlers/worker/tasks.py:on_stop_reason_received()` (7.5-band oqimi)
  `notify_task_stopped`/`notify_client_task_stopped`ni ikkinchi-darajali
  effekt sifatida chaqiradi, lekin Trello izohi haqida kod yo'q.

Natija: Stop bosilgan vaziyat Telegram xabarlarida va bazada ko'rinadi, lekin
Trello kartasining o'zida (ya'ni nazoratchi/rahbar Trello'ni ochib qarasa)
hech qanday iz qolmaydi — TZning aynan shu ko'rinishni talab qilishining
sababi shu: Trello ochilganda kartaning o'zida tarix ko'rinishi kerak.

## Reja

### 1. `bot/trello/client.py`ga yangi metod

```python
async def add_comment_to_card(self, card_id: str, text: str) -> dict:
    """7.5-band: "Stop" bosilganda kartaga izoh yozish uchun (vaqt, kim,
    sabab). Trello kartaning "Activity" tarixida doimiy saqlanadi."""
    return await self._request(
        "POST", f"/cards/{card_id}/actions/comments", params={"text": text}
    )
```

`trello/client.py`dagi boshqa metodlar bilan bir xil naqsh (`_request`
orqali, alohida xatolik ushlash shart emas — chaqiruvchi tomonda
try/except bilan o'raladi, boshqa ikkinchi-darajali Trello chaqiruvlari
kabi).

### 2. `handlers/worker/tasks.py:on_stop_reason_received()` ga qo'shimcha

`stop_log = await timer_service.stop_task(...)` dan keyin, mavjud
`notify_task_stopped`/`notify_client_task_stopped` chaqiruvlari qatoriga
(bir xil try/except naqshida, ikkinchi-darajali effekt sifatida):

```python
try:
    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
    if task is not None and task.trello_card_id:
        comment = (
            f"🛑 To'xtatildi\n"
            f"Vaqt: {format_dt(stop_log.stopped_at)}\n"
            f"Kim: {employee.full_name}\n"
            f"Sabab: {reason}"
        )
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.add_comment_to_card(task.trello_card_id, comment)
except Exception:
    logger.exception("Trello izoh yozishda xatolik (stop_log_id=%s)", stop_log.id)
```

`task.trello_card_id` bo'sh bo'lsa (MISC vazifa, 9-band — Trello'ga umuman
aloqasi yo'q) — jim o'tkazib yuboriladi, xato emas.

Kerakli importlar: `from config import settings`, `from trello.client import
TrelloClient` (`worker/tasks.py`da hozircha yo'q — qo'shilishi kerak).

### 3. Ixtiyoriy kengaytma (TZ so'ramagan, lekin mantiqiy)

`resume_task()` chaqirilganda ham ("Davom ettirish") xuddi shunday qisqa
izoh qo'yish mumkin ("▶️ Davom ettirildi"). TZ buni aniq so'ramagan —
qo'shish/qo'shmaslik ixtiyoriy, MVP uchun shart emas.

## Tekshirish rejasi

Boshqa bo'limlar bilan bir xil naqsh: `bot/_smoke_stop_comment.py` (Test
board'da bitta karta yaratib, Stop bosib, `GET /cards/{id}/actions?filter=
commentCard` orqali izoh borligini tasdiqlash), ishlatilgach o'chiriladi.

## Tugagach

- `shared/db-schema.md`ga o'zgarish kerak emas (yangi ustun yo'q, faqat
  Trello API chaqiruvi).
- Ushbu hujjat `.claude/plans/`dan olib tashlanadi, README'dagi qator ham.
