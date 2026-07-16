"""Tizim sozlamalarini boshqarish (16-band): eslatma vaqti, jarima
ko'paytiruvchisi, brigadir ulushi, kun-siljish balli — hammasi bazada
(`app_settings`) saqlanadi va shu yerdan o'zgartiriladi, kodga tikilmagan.

Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR — `RoleAccessMiddleware` orqali,
modul darajasida routerga ulangan (pastda). Har bir o'zgartirish
`core/logger.py` orqali kim/qachon/nima o'zgartirgani bilan log qilinadi.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.models.employee import Employee
from db.repositories import DepartmentRepository
from jobs import reminder_job
from keyboards.admin_kb import (
    REMINDER_ADD,
    REMINDER_BACK,
    SETTING_FIELD_LABELS,
    SKIP,
    DepartmentAutoReassignToggle,
    DepartmentSelect,
    ReminderEntryDelete,
    ReminderEntryEdit,
    ReminderEntrySelect,
    ReminderUrgencySelect,
    SettingField,
    build_autoreassign_keyboard,
    build_department_keyboard,
    build_reminder_entry_action_keyboard,
    build_reminder_schedule_keyboard,
    build_settings_keyboard,
    build_urgency_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import settings_service
from states.settings_states import DepartmentChainStates, ReminderScheduleStates, SettingsStates
from utils.enums import Role

logger = logging.getLogger(__name__)

router = Router(name="admin_settings")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))
router.callback_query.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))

_PROMPTS = {
    "default_penalty_multiplier": "Yangi jarima ko'paytiruvchisini kiriting (masalan: 1.0):",
    "brigade_share_ratio": "Yangi brigadir ulushini kiriting (0 dan 1 gacha, masalan: 0.33):",
    "balls_per_day_shift": "Har necha minus ball uchun to'lov kuni 1 kunga surilishini kiriting (butun son, masalan: 5):",
}


def _format_value(field: str, snapshot: settings_service.AppSettingsSnapshot) -> str:
    return str(getattr(snapshot, field))


async def _build_settings_text() -> str:
    snapshot = await settings_service.get_settings()
    lines = ["⚙️ Joriy sozlamalar:"]
    for field, label in SETTING_FIELD_LABELS.items():
        lines.append(f"{label}: {_format_value(field, snapshot)}")
    return "\n".join(lines)


def _parse_value(field: str, text: str) -> object:
    text = text.strip()
    if field == "default_penalty_multiplier":
        value = float(text)
        if not (0 < value <= 10):
            raise ValueError("0 dan 10 gacha bo'lishi kerak")
        return value
    if field == "brigade_share_ratio":
        value = float(text)
        if not (0 <= value <= 1):
            raise ValueError("0 dan 1 gacha bo'lishi kerak")
        return value
    if field == "balls_per_day_shift":
        value = int(text)
        if value <= 0:
            raise ValueError("musbat butun son bo'lishi kerak")
        return value
    raise ValueError(f"noma'lum sozlama: {field}")


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    try:
        text = await _build_settings_text()
        await message.answer(text, reply_markup=build_settings_keyboard())
    except Exception:
        logger.exception("cmd_settings xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.callback_query(SettingField.filter())
async def on_setting_field_selected(
    callback: CallbackQuery, callback_data: SettingField, state: FSMContext
) -> None:
    try:
        await state.set_state(SettingsStates.editing_value)
        await state.update_data(field=callback_data.field)

        if callback.message:
            await callback.message.answer(_PROMPTS[callback_data.field])
        await callback.answer()
    except Exception:
        logger.exception("on_setting_field_selected xatosi (field=%s)", callback_data.field)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(SettingsStates.editing_value)
async def on_setting_value_received(message: Message, state: FSMContext, employee: Employee) -> None:
    data = await state.get_data()
    field = data.get("field")
    text = (message.text or "").strip()

    try:
        value = _parse_value(field, text)
    except ValueError as exc:
        await message.answer(f"Noto'g'ri qiymat: {exc}. Qayta kiriting:")
        return
    except Exception:
        logger.exception("on_setting_value_received: parse xatosi (field=%s)", field)
        await state.clear()
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    try:
        await settings_service.update_setting(**{field: value})
    except Exception:
        logger.exception("on_setting_value_received: bazani yangilashda xatolik (field=%s)", field)
        await state.clear()
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await state.clear()

    logger.info(
        "Sozlama o'zgartirildi: %s -> %s (kim: %s, telegram_id=%s)",
        field, value, employee.full_name, employee.telegram_id,
    )

    text_out = await _build_settings_text()
    await message.answer(f"✅ Sozlama yangilandi.\n\n{text_out}", reply_markup=build_settings_keyboard())


async def _list_all_departments():
    async with async_session() as session:
        return await DepartmentRepository(session).list_all()


async def _get_department(department_id: int):
    async with async_session() as session:
        return await DepartmentRepository(session).get_by_id(department_id)


@router.message(Command("deptchain"))
async def cmd_department_chain(message: Message, state: FSMContext) -> None:
    """6.1/7.4-band: bo'limlarning standart ishlab chiqarish ketma-ketligini
    (masalan Stolyar -> Shkurka -> Kraska) sozlash — `task_service.advance_task_stage()`
    shu zanjirga qarab buyurtmani keyingi bosqichga avtomatik o'tkazadi."""
    try:
        departments = await _list_all_departments()
        if not departments:
            await message.answer("Bazada bo'lim topilmadi.")
            return
        await state.set_state(DepartmentChainStates.waiting_for_department)
        await message.answer(
            "Qaysi bo'limning KEYINGI bosqichini sozlamoqchisiz?",
            reply_markup=build_department_keyboard(departments),
        )
    except Exception:
        logger.exception("cmd_department_chain xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.callback_query(DepartmentChainStates.waiting_for_department, DepartmentSelect.filter())
async def on_source_department_selected(
    callback: CallbackQuery, callback_data: DepartmentSelect, state: FSMContext
) -> None:
    try:
        departments = await _list_all_departments()
        # O'z-o'ziga bog'lab qo'ymaslik uchun joriy bo'limni tanlov ro'yxatidan chiqaramiz.
        options = [d for d in departments if d.id != callback_data.department_id]

        await state.update_data(department_id=callback_data.department_id)
        await state.set_state(DepartmentChainStates.waiting_for_next_department)

        if callback.message:
            await callback.message.edit_text(
                "Bu bo'limdan KEYIN qaysi bo'limga o'tadi? "
                "(agar bu so'nggi bosqich bo'lsa, \"O'tkazib yuborish\"ni bosing)",
                reply_markup=build_department_keyboard(options, include_skip=True),
            )
        await callback.answer()
    except Exception:
        logger.exception("on_source_department_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


async def _save_department_chain(
    callback: CallbackQuery, state: FSMContext, *, next_department_id: int | None
) -> None:
    data = await state.get_data()
    await state.clear()

    try:
        async with async_session() as session:
            department_repo = DepartmentRepository(session)
            department = await department_repo.get_by_id(data["department_id"])
            if department is None:
                await callback.answer("Bo'lim topilmadi.", show_alert=True)
                return
            await department_repo.update(department, next_department_id=next_department_id)
            await session.commit()
            department_name = department.name
    except Exception:
        logger.exception("_save_department_chain xatosi (department_id=%s)", data.get("department_id"))
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    next_name = "yo'q (so'nggi bosqich)"
    if next_department_id is not None:
        next_department = await _get_department(next_department_id)
        next_name = next_department.name if next_department else str(next_department_id)

    await callback.answer("Saqlandi ✅")
    if callback.message:
        await callback.message.edit_text(f"✅ \"{department_name}\" -> keyingi bosqich: {next_name}")


@router.callback_query(DepartmentChainStates.waiting_for_next_department, DepartmentSelect.filter())
async def on_next_department_selected(
    callback: CallbackQuery, callback_data: DepartmentSelect, state: FSMContext
) -> None:
    await _save_department_chain(callback, state, next_department_id=callback_data.department_id)


@router.callback_query(DepartmentChainStates.waiting_for_next_department, F.data == SKIP)
async def on_next_department_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_department_chain(callback, state, next_department_id=None)


# ---------- 8.3-band: bo'lim darajasidagi avto-brigadaga-o'tkazish sozlamasi ----------


@router.message(Command("autoreassign"))
async def cmd_autoreassign(message: Message, state: FSMContext) -> None:
    try:
        await state.clear()
        departments = await _list_all_departments()
        if not departments:
            await message.answer("Bazada bo'lim topilmadi.")
            return
        await message.answer(
            "8.3-band: 48 soatdan ortiq kechikkanda avtomatik brigadaga o'tkazish "
            "signali qaysi bo'limlarda yoqilgan bo'lsin?",
            reply_markup=build_autoreassign_keyboard(departments),
        )
    except Exception:
        logger.exception("cmd_autoreassign xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.callback_query(DepartmentAutoReassignToggle.filter())
async def on_autoreassign_toggled(
    callback: CallbackQuery, callback_data: DepartmentAutoReassignToggle
) -> None:
    try:
        async with async_session() as session:
            department_repo = DepartmentRepository(session)
            department = await department_repo.get_by_id(callback_data.department_id)
            if department is None:
                await callback.answer("Bo'lim topilmadi.", show_alert=True)
                return
            await department_repo.update(
                department, auto_reassign_after_48h=not department.auto_reassign_after_48h
            )
            await session.commit()

        departments = await _list_all_departments()
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=build_autoreassign_keyboard(departments))
        await callback.answer("Yangilandi ✅")
    except Exception:
        logger.exception("on_autoreassign_toggled xatosi (department_id=%s)", callback_data.department_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


# ---------- 7.3-band: eslatma jadvali (`/reminders`) ----------


@router.message(Command("reminders"))
async def cmd_reminders(message: Message, state: FSMContext) -> None:
    try:
        await state.clear()
        snapshot = await settings_service.get_settings()
        await message.answer(
            "🕗 Kunlik eslatma jadvali:",
            reply_markup=build_reminder_schedule_keyboard(snapshot.reminder_schedule),
        )
    except Exception:
        logger.exception("cmd_reminders xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.callback_query(F.data == REMINDER_BACK)
async def on_reminders_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    snapshot = await settings_service.get_settings()
    if callback.message:
        await callback.message.edit_text(
            "🕗 Kunlik eslatma jadvali:",
            reply_markup=build_reminder_schedule_keyboard(snapshot.reminder_schedule),
        )
    await callback.answer()


@router.callback_query(ReminderEntrySelect.filter())
async def on_reminder_entry_selected(
    callback: CallbackQuery, callback_data: ReminderEntrySelect, state: FSMContext
) -> None:
    try:
        await state.clear()
        snapshot = await settings_service.get_settings()
        entry = snapshot.reminder_schedule[callback_data.index]
        if callback.message:
            await callback.message.edit_text(
                f"🕗 {entry['time']} — {entry['urgency']}",
                reply_markup=build_reminder_entry_action_keyboard(callback_data.index),
            )
        await callback.answer()
    except IndexError:
        await callback.answer("Bu yozuv allaqachon o'chirilgan.", show_alert=True)
    except Exception:
        logger.exception("on_reminder_entry_selected xatosi (index=%s)", callback_data.index)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(F.data == REMINDER_ADD)
async def on_reminder_add_requested(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(ReminderScheduleStates.waiting_for_time)
        await state.update_data(mode="add")
        if callback.message:
            await callback.message.answer("Yangi eslatma vaqtini kiriting (HH:MM, masalan: 15:00):")
        await callback.answer()
    except Exception:
        logger.exception("on_reminder_add_requested xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(ReminderEntryEdit.filter())
async def on_reminder_edit_requested(
    callback: CallbackQuery, callback_data: ReminderEntryEdit, state: FSMContext
) -> None:
    try:
        await state.set_state(ReminderScheduleStates.waiting_for_time)
        await state.update_data(mode="edit", index=callback_data.index)
        if callback.message:
            await callback.message.answer("Yangi vaqtni kiriting (HH:MM, masalan: 15:00):")
        await callback.answer()
    except Exception:
        logger.exception("on_reminder_edit_requested xatosi (index=%s)", callback_data.index)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(ReminderEntryDelete.filter())
async def on_reminder_delete_requested(
    callback: CallbackQuery, callback_data: ReminderEntryDelete, state: FSMContext, bot: Bot
) -> None:
    try:
        snapshot = await settings_service.get_settings()
        schedule = list(snapshot.reminder_schedule)
        if not 0 <= callback_data.index < len(schedule):
            await callback.answer("Bu yozuv allaqachon o'chirilgan.", show_alert=True)
            return

        del schedule[callback_data.index]
        updated = await settings_service.update_setting(reminder_schedule=schedule)
        reminder_job.schedule_all(bot, updated.reminder_schedule)

        await state.clear()
        if callback.message:
            await callback.message.edit_text(
                "🕗 Kunlik eslatma jadvali:",
                reply_markup=build_reminder_schedule_keyboard(updated.reminder_schedule),
            )
        await callback.answer("O'chirildi ✅")
    except Exception:
        logger.exception("on_reminder_delete_requested xatosi (index=%s)", callback_data.index)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(Command("cancel"), StateFilter(ReminderScheduleStates))
async def cmd_cancel_reminder(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.message(ReminderScheduleStates.waiting_for_time)
async def on_reminder_time_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        hour, minute = text.split(":")
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError
    except ValueError:
        await message.answer("Format noto'g'ri. Masalan: 15:00 shaklida kiriting:")
        return

    await state.update_data(time=f"{int(hour):02d}:{int(minute):02d}")
    await state.set_state(ReminderScheduleStates.waiting_for_urgency)
    await message.answer("Eskalatsiya darajasini tanlang:", reply_markup=build_urgency_keyboard())


@router.callback_query(ReminderScheduleStates.waiting_for_urgency, ReminderUrgencySelect.filter())
async def on_reminder_urgency_selected(
    callback: CallbackQuery, callback_data: ReminderUrgencySelect, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    await state.clear()

    try:
        snapshot = await settings_service.get_settings()
        schedule = list(snapshot.reminder_schedule)
        new_entry = {"time": data["time"], "urgency": callback_data.urgency}

        if data.get("mode") == "edit":
            schedule[data["index"]] = new_entry
        else:
            schedule.append(new_entry)

        updated = await settings_service.update_setting(reminder_schedule=schedule)
        reminder_job.schedule_all(bot, updated.reminder_schedule)
    except settings_service.InvalidReminderScheduleError as exc:
        await callback.answer()
        if callback.message:
            await callback.message.answer(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_reminder_urgency_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)
        return

    await callback.answer("Saqlandi ✅")
    if callback.message:
        await callback.message.answer(
            "🕗 Kunlik eslatma jadvali:",
            reply_markup=build_reminder_schedule_keyboard(updated.reminder_schedule),
        )
