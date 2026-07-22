"""Mini App'ni ochadigan tugma — barcha rol menyularida qayta ishlatiladi.
`config.settings.miniapp_base_url` sozlanmagan bo'lsa (masalan lokal
ishlab chiqishda, Railway public domain hali yoqilmagan) `None` qaytadi —
chaqiruvchi bunday holda tugmani chatga umuman qo'shmaydi, aks holda
Telegram bo'sh/https bo'lmagan URL bilan xato qaytaradi."""

from aiogram.types import InlineKeyboardButton, WebAppInfo

from config import settings

MINIAPP_BUTTON_TEXT = "📱 Ilovani ochish"


def build_miniapp_button() -> InlineKeyboardButton | None:
    if not settings.miniapp_base_url:
        return None
    return InlineKeyboardButton(text=MINIAPP_BUTTON_TEXT, web_app=WebAppInfo(url=settings.miniapp_base_url))
