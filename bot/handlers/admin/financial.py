"""8.6-band admin UI: moliyaviy taklif summalarini qo'lda kiritish
(3-bosqichda ataylab qoldirilgan, 4-bosqichga rejalashtirilgan qism —
`services/financial_service.py` docstringiga qarang). Tizimda moliya moduli
yo'q, shu sabab ikkala qoida uchun ham manba (mijoz to'lovi/avans/buyurtma
summasi) HAR DOIM shu yerda qo'lda kiritiladi.

Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR."""

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.repositories import FinancialSuggestionRepository, TaskRepository
from keyboards.admin_kb import (
    CANCEL,
    CONFIRM,
    FinancialSuggestionSelect,
    build_financial_suggestions_keyboard,
    build_yes_no_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import financial_service
from states.financial_states import AdvanceWaiverStates, WageDeductionAmountStates
from utils.enums import Role

logger = logging.getLogger(__name__)

router = Router(name="admin_financial")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))
router.callback_query.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))


# ---------- 1-qoida: wage deduction summasini kiritish ----------


@router.message(Command("moliyaviy"))
async def cmd_financial(message: Message, state: FSMContext) -> None:
    try:
        await state.clear()
        async with async_session() as session:
            suggestions = await FinancialSuggestionRepository(session).list_pending_amount_entry()

        if not suggestions:
            await message.answer("Summasi kutilayotgan moliyaviy taklif yo'q.")
            return

        await message.answer(
            "💰 Summasi kutilayotgan takliflar (8.6-band 1-qoida):",
            reply_markup=build_financial_suggestions_keyboard(suggestions),
        )
    except Exception:
        logger.exception("cmd_financial xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.callback_query(FinancialSuggestionSelect.filter())
async def on_suggestion_selected(
    callback: CallbackQuery, callback_data: FinancialSuggestionSelect, state: FSMContext
) -> None:
    try:
        await state.set_state(WageDeductionAmountStates.waiting_for_amount)
        await state.update_data(suggestion_id=callback_data.suggestion_id)
        if callback.message:
            await callback.message.answer("Mijoz ushlab qolgan summani kiriting (masalan: 1500000):")
        await callback.answer()
    except Exception:
        logger.exception("on_suggestion_selected xatosi (suggestion_id=%s)", callback_data.suggestion_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(WageDeductionAmountStates.waiting_for_amount)
async def on_amount_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        amount = float(text)
        if amount < 0:
            raise ValueError
    except ValueError:
        await message.answer("Noto'g'ri summa. Musbat son kiriting (masalan: 1500000):")
        return

    data = await state.get_data()
    await state.clear()

    try:
        suggestion = await financial_service.set_wage_deduction_amount(data["suggestion_id"], amount)
    except Exception:
        logger.exception("on_amount_received xatosi (suggestion_id=%s)", data.get("suggestion_id"))
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await message.answer(
        f"✅ Saqlandi. Taklif qilingan ushlab qolish summasi: {suggestion.suggested_deduction_amount:,.0f}"
    )


# ---------- 2-qoida: advance waiver ----------


@router.message(Command("avanskechirim"))
async def cmd_advance_waiver(message: Message, state: FSMContext) -> None:
    try:
        await state.set_state(AdvanceWaiverStates.waiting_for_task_id)
        await message.answer("8.6-band 2-qoida: vazifa (task) ID raqamini kiriting:")
    except Exception:
        logger.exception("cmd_advance_waiver xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.message(Command("cancel"), StateFilter(AdvanceWaiverStates))
async def cmd_cancel_advance_waiver(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.message(AdvanceWaiverStates.waiting_for_task_id)
async def on_task_id_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        task_id = int(text)
    except ValueError:
        await message.answer("Noto'g'ri ID. Butun son kiriting:")
        return

    async with async_session() as session:
        task = await TaskRepository(session).get_by_id(task_id)
    if task is None:
        await message.answer(f"Task #{task_id} topilmadi. Qayta kiriting yoki /cancel:")
        return

    await state.update_data(task_id=task_id)
    await state.set_state(AdvanceWaiverStates.waiting_for_advance_percent)
    await message.answer("Avans necha % olingan (0-100):")


@router.message(AdvanceWaiverStates.waiting_for_advance_percent)
async def on_advance_percent_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        percent = int(text)
        if not (0 <= percent <= 100):
            raise ValueError
    except ValueError:
        await message.answer("0 dan 100 gacha butun son kiriting:")
        return

    await state.update_data(advance_percent_paid=percent)
    await state.set_state(AdvanceWaiverStates.waiting_for_order_value)
    await message.answer("Buyurtma umumiy summasini kiriting (masalan: 10000000):")


@router.message(AdvanceWaiverStates.waiting_for_order_value)
async def on_order_value_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        value = float(text)
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Noto'g'ri summa. Musbat son kiriting:")
        return

    await state.update_data(order_total_value=value)
    await state.set_state(AdvanceWaiverStates.waiting_for_is_late)
    await message.answer("Buyurtma muddati kechikkanmi?", reply_markup=build_yes_no_keyboard())


@router.callback_query(AdvanceWaiverStates.waiting_for_is_late, F.data.in_({CONFIRM, CANCEL}))
async def on_is_late_selected(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        await state.clear()

        suggestion = await financial_service.create_advance_waiver_suggestion(
            data["task_id"],
            advance_percent_paid=data["advance_percent_paid"],
            is_late=callback.data == CONFIRM,
            order_total_value=data["order_total_value"],
        )

        if suggestion.applicable:
            text = f"✅ Taklif yaratildi. Kechiriladigan summa: {suggestion.waived_amount:,.0f}"
        else:
            text = "✅ Taklif yaratildi, lekin shartlar bajarilmadi (applicable=False)."

        if callback.message:
            await callback.message.edit_text(text)
        await callback.answer()
    except Exception:
        logger.exception("on_is_late_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
