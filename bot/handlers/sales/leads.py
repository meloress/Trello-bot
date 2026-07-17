"""13-band: Sotuvchi (Role.SELLER) uchun lid varonkasi + qo'ng'iroqlar
bazasi. Ishlab chiqarish handlerlaridan (worker/admin) mustaqil — o'z rol
tekshiruvi, o'z FSM oqimi."""

import logging

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.repositories import EmployeeRepository, LeadRepository
from keyboards.sales_kb import (
    STAGE_LABELS,
    BrandSelect,
    LeadAdvance,
    LeadCallLogStart,
    LeadClose,
    LeadSelect,
    build_brand_keyboard,
    build_lead_detail_keyboard,
    build_lead_list_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import sales_service
from states.sales_states import CallLogStates, CreateLeadStates
from utils.enums import LeadBrand, Role

logger = logging.getLogger(__name__)

router = Router(name="sales_leads")
router.message.middleware(RoleAccessMiddleware({Role.SELLER}))
router.callback_query.middleware(RoleAccessMiddleware({Role.SELLER}))


@router.message(Command("yangilid"))
async def cmd_new_lead(message: Message, state: FSMContext) -> None:
    try:
        await state.set_state(CreateLeadStates.waiting_for_brand)
        await message.answer("Qaysi brand uchun yangi lid?", reply_markup=build_brand_keyboard())
    except Exception:
        logger.exception("cmd_new_lead xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.message(Command("cancel"), StateFilter(CreateLeadStates))
async def cmd_cancel_new_lead(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.callback_query(CreateLeadStates.waiting_for_brand, BrandSelect.filter())
async def on_brand_selected(callback: CallbackQuery, callback_data: BrandSelect, state: FSMContext) -> None:
    try:
        await state.update_data(brand=callback_data.brand)
        await state.set_state(CreateLeadStates.waiting_for_phone)
        if callback.message:
            await callback.message.edit_text("Mijoz telefon raqamini kiriting:")
        await callback.answer()
    except Exception:
        logger.exception("on_brand_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(CreateLeadStates.waiting_for_phone)
async def on_lead_phone_received(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if not phone:
        await message.answer("Telefon raqami bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return
    await state.update_data(phone=phone)
    await state.set_state(CreateLeadStates.waiting_for_name)
    await message.answer("Mijoz F.I.Sh. kiriting:")


@router.message(CreateLeadStates.waiting_for_name)
async def on_lead_name_received(message: Message, state: FSMContext, employee) -> None:
    full_name = (message.text or "").strip()
    if not full_name:
        await message.answer("Ism bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return

    data = await state.get_data()
    await state.clear()

    try:
        lead = await sales_service.create_lead(
            brand=LeadBrand(data["brand"]),
            client_phone=data["phone"],
            client_full_name=full_name,
            seller_id=employee.id,
        )
    except sales_service.SalesBoardNotConfiguredError as exc:
        await message.answer(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_lead_name_received xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await message.answer(f"✅ Lid yaratildi (#{lead.id}), Trello karta: {lead.trello_card_id}")


@router.message(Command("lidlarim"))
async def cmd_my_leads(message: Message, state: FSMContext, employee) -> None:
    try:
        await state.clear()
        async with async_session() as session:
            leads = await LeadRepository(session).list_by_seller(employee.id)

        if not leads:
            await message.answer("Sizda ochiq lid yo'q.")
            return

        await message.answer("Sizning ochiq lidlaringiz:", reply_markup=build_lead_list_keyboard(leads))
    except Exception:
        logger.exception("cmd_my_leads xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


async def _show_lead_detail(answer_func, lead_id: int) -> None:
    async with async_session() as session:
        lead = await LeadRepository(session).get_by_id(lead_id)
    if lead is None:
        await answer_func("Lid topilmadi.")
        return
    text = f"Lid #{lead.id} — {STAGE_LABELS.get(lead.stage.value, lead.stage.value)}"
    await answer_func(text, reply_markup=build_lead_detail_keyboard(lead))


@router.callback_query(LeadSelect.filter())
async def on_lead_selected(callback: CallbackQuery, callback_data: LeadSelect) -> None:
    try:
        if callback.message:
            await _show_lead_detail(callback.message.edit_text, callback_data.lead_id)
        await callback.answer()
    except Exception:
        logger.exception("on_lead_selected xatosi (lead_id=%s)", callback_data.lead_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(LeadAdvance.filter())
async def on_lead_advance(callback: CallbackQuery, callback_data: LeadAdvance) -> None:
    try:
        await sales_service.advance_lead_stage(callback_data.lead_id)
    except (
        sales_service.LeadNotFoundError,
        sales_service.InvalidLeadStateError,
        sales_service.SalesBoardNotConfiguredError,
    ) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        logger.exception("on_lead_advance xatosi (lead_id=%s)", callback_data.lead_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    if callback.message:
        await _show_lead_detail(callback.message.edit_text, callback_data.lead_id)
    await callback.answer("Yangilandi ✅")


@router.callback_query(LeadClose.filter())
async def on_lead_close(callback: CallbackQuery, callback_data: LeadClose) -> None:
    try:
        await sales_service.close_lead(callback_data.lead_id, won=callback_data.won)
    except (
        sales_service.LeadNotFoundError,
        sales_service.InvalidLeadStateError,
        sales_service.SalesBoardNotConfiguredError,
    ) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        logger.exception("on_lead_close xatosi (lead_id=%s)", callback_data.lead_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    if callback.message:
        await _show_lead_detail(callback.message.edit_text, callback_data.lead_id)
    await callback.answer("Yopildi ✅")


@router.callback_query(LeadCallLogStart.filter())
async def on_call_log_start(callback: CallbackQuery, callback_data: LeadCallLogStart, state: FSMContext) -> None:
    try:
        await state.set_state(CallLogStates.waiting_for_content)
        await state.update_data(lead_id=callback_data.lead_id)
        if callback.message:
            await callback.message.answer("Qo'ng'iroq haqida matn yozing yoki ovozli xabar yuboring:")
        await callback.answer()
    except Exception:
        logger.exception("on_call_log_start xatosi (lead_id=%s)", callback_data.lead_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(Command("cancel"), StateFilter(CallLogStates))
async def cmd_cancel_call_log(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.message(CallLogStates.waiting_for_content)
async def on_call_log_content_received(message: Message, state: FSMContext, employee) -> None:
    data = await state.get_data()
    await state.clear()

    content = message.text if message.text else None
    audio_file_id = message.voice.file_id if message.voice else None

    if not content and not audio_file_id:
        await message.answer("Matn yoki ovozli xabar kerak. Qayta urinib ko'ring: /lidlarim")
        return

    try:
        await sales_service.add_call_log(
            data["lead_id"], employee.id, content=content, audio_file_id=audio_file_id
        )
    except sales_service.LeadNotFoundError as exc:
        await message.answer(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_call_log_content_received xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await message.answer("✅ Qo'ng'iroq yozuvi saqlandi.")
