"""Mijoz o'z Telegram akkauntini bog'lash (12-band). Admin vazifa yaratishda
mijozni telefon raqami bilan oldindan kiritadi (`telegram_id=NULL`); mijoz
`/mijoz` bosib Telegram'ning o'z kontakt-ulashish tugmasi orqali shu telefon
raqamini yuborsa, avtomatik xabarnomalar unga ham yetib boradi
(`registration_service` bilan bir xil naqsh — 5.2-band). Qo'lda yozilgan
raqam endi qabul qilinmaydi — u Telegram tomonidan tasdiqlanmagani uchun
boshqa birovning raqamini yozib uning nomidan bog'lanish mumkin bo'lardi."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from services import client_service
from states.client_states import ClientLinkStates

logger = logging.getLogger(__name__)

router = Router(name="common_client_link")

_CONTACT_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


@router.message(Command("mijoz"))
async def cmd_client_link(message: Message, state: FSMContext) -> None:
    try:
        await state.set_state(ClientLinkStates.waiting_for_contact)
        await message.answer(
            "Buyurtmalaringiz haqida avtomatik xabar olish uchun pastdagi tugma orqali telefon "
            "raqamingizni yuboring (rahbar sizni shu raqam bilan tizimga kiritgan bo'lishi kerak):",
            reply_markup=_CONTACT_KEYBOARD,
        )
    except Exception:
        logger.exception("cmd_client_link xatosi (telegram_id=%s)", message.from_user.id)
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.message(ClientLinkStates.waiting_for_contact, F.contact)
async def on_client_contact_received(message: Message, state: FSMContext) -> None:
    if message.contact.user_id != message.from_user.id:
        await message.answer(
            "Iltimos, FAQAT o'zingizning telefon raqamingizni yuboring — pastdagi tugmani bosing:",
            reply_markup=_CONTACT_KEYBOARD,
        )
        return

    phone = message.contact.phone_number

    try:
        client = await client_service.link_client_to_telegram(phone, message.from_user.id)
    except client_service.ClientNotFoundError:
        await message.answer(
            f"'{phone}' raqami bilan mijoz topilmadi. Raqamni tekshiring "
            "yoki rahbarga murojaat qiling."
        )
        return
    except client_service.ClientAlreadyLinkedError:
        await state.clear()
        await message.answer("Bu raqam allaqachon boshqa Telegram akkauntga bog'langan. Rahbarga murojaat qiling.")
        return
    except Exception:
        logger.exception("on_client_contact_received xatosi (phone=%s)", phone)
        await state.clear()
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await state.clear()
    logger.info("Mijoz Telegramga bog'landi: %s (telegram_id=%s)", client.full_name, client.telegram_id)
    await message.answer(f"✅ Muvaffaqiyatli bog'landingiz, {client.full_name}! Endi xabarnomalar shu yerga keladi.")


@router.message(ClientLinkStates.waiting_for_contact)
async def on_client_non_contact_message(message: Message) -> None:
    """Xavfsizlik uchun qo'lda yozilgan raqam endi qabul qilinmaydi — faqat
    Telegram tomonidan tasdiqlangan kontakt orqali bog'lanish mumkin."""
    await message.answer(
        "Iltimos, pastdagi tugmani bosib telefon raqamingizni yuboring — qo'lda yozish qabul qilinmaydi:",
        reply_markup=_CONTACT_KEYBOARD,
    )
