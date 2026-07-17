"""Mijoz o'z Telegram akkauntini bog'lash (12-band). Admin vazifa yaratishda
mijozni telefon raqami bilan oldindan kiritadi (`telegram_id=NULL`); mijoz
`/mijoz` bosib o'sha telefon raqamini kiritsa, avtomatik xabarnomalar unga
ham yetib boradi (`registration_service` bilan bir xil naqsh — 5.2-band)."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from services import client_service
from states.client_states import ClientLinkStates

logger = logging.getLogger(__name__)

router = Router(name="common_client_link")


@router.message(Command("mijoz"))
async def cmd_client_link(message: Message, state: FSMContext) -> None:
    try:
        await state.set_state(ClientLinkStates.waiting_for_phone)
        await message.answer(
            "Buyurtmalaringiz haqida avtomatik xabar olish uchun telefon raqamingizni kiriting "
            "(rahbar sizni shu raqam bilan tizimga kiritgan bo'lishi kerak):"
        )
    except Exception:
        logger.exception("cmd_client_link xatosi (telegram_id=%s)", message.from_user.id)
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.message(ClientLinkStates.waiting_for_phone)
async def on_client_phone_received(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if not phone:
        await message.answer("Telefon raqami bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return

    try:
        client = await client_service.link_client_to_telegram(phone, message.from_user.id)
    except client_service.ClientNotFoundError:
        await message.answer(
            f"'{phone}' raqami bilan mijoz topilmadi. Raqamni tekshirib qayta kiriting "
            "yoki rahbarga murojaat qiling."
        )
        return
    except client_service.ClientAlreadyLinkedError:
        await state.clear()
        await message.answer("Bu raqam allaqachon boshqa Telegram akkauntga bog'langan. Rahbarga murojaat qiling.")
        return
    except Exception:
        logger.exception("on_client_phone_received xatosi (phone=%s)", phone)
        await state.clear()
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await state.clear()
    logger.info("Mijoz Telegramga bog'landi: %s (telegram_id=%s)", client.full_name, client.telegram_id)
    await message.answer(f"✅ Muvaffaqiyatli bog'landingiz, {client.full_name}! Endi xabarnomalar shu yerga keladi.")
