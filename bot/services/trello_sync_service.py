"""Trello karta LABEL (rang) avtomatikasi (6.3-band).

Trello'ning o'zida muddatga qarab avtomatik rang almashtirish yo'q — bu servis
har bir vazifaning muddatiga qarab kerakli STATUS LABEL'ni (Bajarilmoqda /
Bugun tugaydi / Muddati o'tgan) board'dan topib (yoki hali yo'q bo'lsa
yaratib), kartaga qo'yadi va ESKI status-labelni olib tashlaydi — bir vaqtda
kartada faqat BITTA status rangi bo'ladi, eskilari to'planib qolmaydi.
"""

import logging
from datetime import datetime, timezone

from config import settings
from trello.client import TrelloAPIError, TrelloClient
from utils.formatters import TASHKENT_TZ

logger = logging.getLogger(__name__)


class CardStatus:
    IN_PROGRESS = "in_progress"
    DUE_TODAY = "due_today"
    OVERDUE = "overdue"


# status -> (label nomi, Trello rang kodi). Trello rang palitrasi fiksirlangan
# to'plamdan iborat (green/yellow/orange/red/purple/blue/sky/lime/pink/black).
_LABEL_SPECS: dict[str, tuple[str, str]] = {
    CardStatus.IN_PROGRESS: ("Bajarilmoqda", "green"),
    CardStatus.DUE_TODAY: ("Bugun tugaydi", "yellow"),
    CardStatus.OVERDUE: ("Muddati o'tgan", "red"),
}
_STATUS_LABEL_NAMES = {name for name, _color in _LABEL_SPECS.values()}


class TrelloLabelNotFoundError(Exception):
    """Karta yoki uning board'i Trello'da topilmadi (404) — karta boshqa
    joyga ko'chirilgan yoki butunlay o'chirilgan bo'lishi mumkin."""


def determine_status(deadline: datetime, *, now: datetime | None = None) -> str:
    """Muddatga qarab status aniqlaydi. "Bugun" — Toshkent mahalliy sanasi
    bo'yicha (UTC emas), chunki xodim va rahbar shu vaqt zonasida ishlaydi."""
    now = now or datetime.now(timezone.utc)
    if now > deadline:
        return CardStatus.OVERDUE
    if now.astimezone(TASHKENT_TZ).date() == deadline.astimezone(TASHKENT_TZ).date():
        return CardStatus.DUE_TODAY
    return CardStatus.IN_PROGRESS


async def update_card_label(card_id: str, status: str) -> None:
    """Kartaga `status`ga mos labelni qo'yadi, boshqa status-labellarni olib
    tashlaydi. Karta/board topilmasa `TrelloLabelNotFoundError` ko'taradi —
    chaqiruvchi (job) buni log qilib, boshqa vazifalarni tekshirishni
    davom ettirishi kerak. Bitta labelning o'zi topilmasa (404, masalan
    board'dan qo'lda o'chirib tashlangan bo'lsa) — jarayon TO'XTAMAYDI,
    faqat "404 Label Not Found" deb log qilinadi."""
    if status not in _LABEL_SPECS:
        raise ValueError(f"noma'lum status: {status}")

    target_name, target_color = _LABEL_SPECS[status]

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as client:
        try:
            card = await client.get_card(card_id)
        except TrelloAPIError as exc:
            if exc.status == 404:
                raise TrelloLabelNotFoundError(f"Karta topilmadi: {card_id}") from exc
            raise

        board_id = card.get("idBoard")
        current_label_ids = set(card.get("idLabels") or [])

        try:
            board_labels = await client.list_board_labels(board_id)
        except TrelloAPIError as exc:
            if exc.status == 404:
                raise TrelloLabelNotFoundError(f"Board topilmadi: {board_id} (karta {card_id})") from exc
            raise

        target_label = next((label for label in board_labels if label.get("name") == target_name), None)
        if target_label is None:
            target_label = await client.create_label(board_id, target_name, target_color)

        other_status_label_ids = {
            label["id"]
            for label in board_labels
            if label.get("name") in _STATUS_LABEL_NAMES and label.get("name") != target_name
        }

        for label_id in current_label_ids & other_status_label_ids:
            try:
                await client.remove_label_from_card(card_id, label_id)
            except TrelloAPIError as exc:
                if exc.status == 404:
                    logger.warning(
                        "404 Label Not Found: label %s karta %s'dan olib tashlanmadi (allaqachon yo'q)",
                        label_id,
                        card_id,
                    )
                else:
                    raise

        if target_label["id"] not in current_label_ids:
            try:
                await client.add_label_to_card(card_id, target_label["id"])
            except TrelloAPIError as exc:
                if exc.status == 404:
                    logger.warning(
                        "404 Label Not Found: label %s karta %s'ga qo'shilmadi",
                        target_label["id"],
                        card_id,
                    )
                else:
                    raise
