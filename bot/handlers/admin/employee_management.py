"""Xodimlar bazasi moduli — CRUD Telegram bot orqali (5.1-band).

Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR — RoleAccessMiddleware orqali.

Oqim: `/employees` -> ro'yxat (+ "Yangi qo'shish" tugmasi) -> bitta xodimni
tanlash -> tafsilot (Tahrirlash / Faollik / O'chirish / Ro'yxatga qaytish).
FSM state faqat "hozir nima kutilyapti"ni bildiradi; "qaysi xodim bilan
ishlayapmiz" doim FSM DATA'da (`employee_id`) saqlanadi — settings.py'dagi
bitta-holat-ko'p-maydon uslubiga mos.
"""

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database import async_session
from db.models.employee import Employee
from db.repositories import BrigadeRepository, DepartmentRepository, EmployeeRepository
from keyboards.admin_kb import (
    CANCEL,
    CONFIRM,
    EMP_ADD,
    EMP_BACK_TO_DETAIL,
    EMP_DELETE,
    EMP_EDIT,
    EMP_LIST,
    EMP_TOGGLE_ACTIVE,
    EMPLOYEE_FIELD_LABELS,
    ROLE_LABELS,
    SKIP,
    BrigadeSelect,
    DepartmentSelect,
    EmployeeFieldSelect,
    EmployeeSelect,
    RoleSelect,
    build_brigade_keyboard,
    build_department_keyboard,
    build_employee_detail_keyboard,
    build_employee_edit_fields_keyboard,
    build_employee_list_keyboard,
    build_role_keyboard,
    build_yes_no_keyboard,
)
from middlewares.auth import RoleAccessMiddleware
from services import employee_service
from states.employee_states import EmployeeManageStates
from utils.enums import Role

logger = logging.getLogger(__name__)

router = Router(name="admin_employee_management")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))
router.callback_query.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))

_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def _validate_phone(text: str) -> str:
    normalized = text.strip().replace(" ", "").replace("-", "")
    if not _PHONE_RE.match(normalized):
        raise ValueError("format noto'g'ri (masalan: +998901234567)")
    return normalized


async def _list_all_employees() -> list[Employee]:
    async with async_session() as session:
        return await EmployeeRepository(session).list_all()


async def _list_all_departments():
    async with async_session() as session:
        return await DepartmentRepository(session).list_all()


async def _list_brigades_for_department(department_id: int):
    async with async_session() as session:
        return await BrigadeRepository(session).list_by_department(department_id)


async def _format_employee_detail(employee: Employee) -> str:
    async with async_session() as session:
        department = (
            await DepartmentRepository(session).get_by_id(employee.department_id)
            if employee.department_id
            else None
        )
        brigade = (
            await BrigadeRepository(session).get_by_id(employee.brigade_id)
            if employee.brigade_id
            else None
        )

    return "\n".join(
        [
            f"👤 {employee.full_name}",
            f"Holat: {'✅ Faol' if employee.is_active else '🚫 Nofaol'}",
            f"Rol: {ROLE_LABELS.get(employee.role, employee.role.value)}",
            f"Telefon: {employee.phone_number or '-'}",
            f"Bo'lim: {department.name if department else '-'}",
            f"Brigada: {brigade.name if brigade else '-'}",
            f"Telegram: {'bog‘langan' if employee.telegram_id else 'bog‘lanmagan'}",
        ]
    )


async def _refresh_detail(callback: CallbackQuery, employee_id: int) -> None:
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_id(employee_id)
    if employee is None:
        if callback.message:
            await callback.message.edit_text("Xodim topilmadi (o'chirilgan bo'lishi mumkin).")
        return
    text = await _format_employee_detail(employee)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_employee_detail_keyboard(employee))


# ---------- Ro'yxat va tafsilot ----------


@router.message(Command("employees"))
async def cmd_employees(message: Message, state: FSMContext) -> None:
    try:
        await state.clear()
        employees = await _list_all_employees()
        await message.answer("👥 Xodimlar ro'yxati:", reply_markup=build_employee_list_keyboard(employees))
    except Exception:
        logger.exception("cmd_employees xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")


@router.message(Command("cancel"), StateFilter(EmployeeManageStates))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Amal bekor qilindi.")


@router.callback_query(F.data == EMP_LIST)
async def on_back_to_list(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
        employees = await _list_all_employees()
        if callback.message:
            await callback.message.edit_text(
                "👥 Xodimlar ro'yxati:", reply_markup=build_employee_list_keyboard(employees)
            )
        await callback.answer()
    except Exception:
        logger.exception("on_back_to_list xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeSelect.filter())
async def on_employee_selected(
    callback: CallbackQuery, callback_data: EmployeeSelect, state: FSMContext
) -> None:
    try:
        await state.clear()
        await state.update_data(employee_id=callback_data.employee_id)
        await _refresh_detail(callback, callback_data.employee_id)
        await callback.answer()
    except Exception:
        logger.exception("on_employee_selected xatosi (employee_id=%s)", callback_data.employee_id)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(F.data == EMP_BACK_TO_DETAIL)
async def on_back_to_detail(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        await state.set_state(None)
        await _refresh_detail(callback, employee_id)
        await callback.answer()
    except Exception:
        logger.exception("on_back_to_detail xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(F.data == EMP_TOGGLE_ACTIVE)
async def on_toggle_active(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        if employee_id is None:
            await callback.answer("Xodim aniqlanmadi.", show_alert=True)
            return

        async with async_session() as session:
            employee = await EmployeeRepository(session).get_by_id(employee_id)
        if employee is None:
            await callback.answer("Xodim topilmadi.", show_alert=True)
            return

        if employee.is_active:
            await employee_service.deactivate_employee(employee_id)
        else:
            await employee_service.reactivate_employee(employee_id)

        await _refresh_detail(callback, employee_id)
        await callback.answer("Holat yangilandi ✅")
    except Exception:
        logger.exception("on_toggle_active xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


# ---------- O'chirish (soft-delete) ----------


@router.callback_query(F.data == EMP_DELETE)
async def on_delete_requested(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        if data.get("employee_id") is None:
            await callback.answer("Xodim aniqlanmadi.", show_alert=True)
            return

        await state.set_state(EmployeeManageStates.delete_confirming)
        if callback.message:
            await callback.message.edit_text(
                "Haqiqatan ham bu xodimni o'chirmoqchimisiz?\n"
                "(Bu — nofaol qilish, tarix saqlanadi, keyin qayta faollashtirish mumkin)",
                reply_markup=build_yes_no_keyboard(),
            )
        await callback.answer()
    except Exception:
        logger.exception("on_delete_requested xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.delete_confirming, F.data == CANCEL)
async def on_delete_cancelled(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        await state.set_state(None)
        await _refresh_detail(callback, employee_id)
        await callback.answer("Bekor qilindi")
    except Exception:
        logger.exception("on_delete_cancelled xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.delete_confirming, F.data == CONFIRM)
async def on_delete_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        await employee_service.deactivate_employee(employee_id)
        await state.set_state(None)
        await _refresh_detail(callback, employee_id)
        await callback.answer("Xodim nofaol qilindi ✅")
    except employee_service.EmployeeNotFoundError:
        await callback.answer("Xodim topilmadi.", show_alert=True)
    except Exception:
        logger.exception("on_delete_confirmed xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


# ---------- Tahrirlash ----------


@router.callback_query(F.data == EMP_EDIT)
async def on_edit_requested(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        if data.get("employee_id") is None:
            await callback.answer("Xodim aniqlanmadi.", show_alert=True)
            return

        if callback.message:
            await callback.message.edit_text(
                "Qaysi maydonni tahrirlaysiz?", reply_markup=build_employee_edit_fields_keyboard()
            )
        await callback.answer()
    except Exception:
        logger.exception("on_edit_requested xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeFieldSelect.filter())
async def on_field_selected(
    callback: CallbackQuery, callback_data: EmployeeFieldSelect, state: FSMContext
) -> None:
    try:
        field = callback_data.field
        await state.update_data(field=field)

        if field == "role":
            await state.set_state(EmployeeManageStates.edit_waiting_role)
            if callback.message:
                await callback.message.edit_text("Yangi rolni tanlang:", reply_markup=build_role_keyboard())

        elif field == "department_id":
            departments = await _list_all_departments()
            await state.set_state(EmployeeManageStates.edit_waiting_department)
            if callback.message:
                await callback.message.edit_text(
                    "Yangi bo'limni tanlang:",
                    reply_markup=build_department_keyboard(departments, include_skip=True),
                )

        elif field == "brigade_id":
            data = await state.get_data()
            async with async_session() as session:
                employee = await EmployeeRepository(session).get_by_id(data.get("employee_id"))
            if employee is None or employee.department_id is None:
                await callback.answer("Avval bo'lim belgilangan bo'lishi kerak.", show_alert=True)
                return
            brigades = await _list_brigades_for_department(employee.department_id)
            await state.set_state(EmployeeManageStates.edit_waiting_brigade)
            if callback.message:
                await callback.message.edit_text(
                    "Yangi brigadani tanlang:", reply_markup=build_brigade_keyboard(brigades)
                )

        else:  # full_name yoki phone_number
            await state.set_state(EmployeeManageStates.edit_waiting_text_value)
            label = EMPLOYEE_FIELD_LABELS.get(field, field)
            if callback.message:
                await callback.message.answer(f"{label} uchun yangi qiymatni kiriting:")

        await callback.answer()
    except Exception:
        logger.exception("on_field_selected xatosi (field=%s)", callback_data.field)
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(EmployeeManageStates.edit_waiting_text_value)
async def on_edit_text_value_received(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("field")
    employee_id = data.get("employee_id")
    text = (message.text or "").strip()

    try:
        if field == "phone_number":
            value = _validate_phone(text)
        elif field == "full_name":
            if not text:
                await message.answer("Ism bo'sh bo'lishi mumkin emas. Qayta kiriting:")
                return
            value = text
        else:
            raise ValueError(f"noma'lum maydon: {field}")
    except ValueError as exc:
        await message.answer(f"Noto'g'ri qiymat: {exc}. Qayta kiriting:")
        return

    try:
        employee = await employee_service.update_employee(employee_id, **{field: value})
    except employee_service.DuplicateNameError:
        await message.answer("Bu ism bilan boshqa xodim allaqachon mavjud. Boshqa ism kiriting:")
        return
    except employee_service.DuplicatePhoneError:
        await message.answer("Bu telefon raqami bilan boshqa xodim allaqachon mavjud. Boshqa raqam kiriting:")
        return
    except employee_service.EmployeeNotFoundError:
        await state.clear()
        await message.answer("Xodim topilmadi.")
        return
    except Exception:
        logger.exception("on_edit_text_value_received xatosi (field=%s)", field)
        await state.clear()
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    await state.set_state(None)
    text_out = await _format_employee_detail(employee)
    await message.answer(f"✅ Yangilandi.\n\n{text_out}", reply_markup=build_employee_detail_keyboard(employee))


@router.callback_query(EmployeeManageStates.edit_waiting_role, RoleSelect.filter())
async def on_edit_role_selected(
    callback: CallbackQuery, callback_data: RoleSelect, state: FSMContext
) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        await employee_service.update_employee(employee_id, role=Role(callback_data.role))
        await state.set_state(None)
        await _refresh_detail(callback, employee_id)
        await callback.answer("Rol yangilandi ✅")
    except employee_service.EmployeeNotFoundError:
        await callback.answer("Xodim topilmadi.", show_alert=True)
    except Exception:
        logger.exception("on_edit_role_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.edit_waiting_department, DepartmentSelect.filter())
async def on_edit_department_selected(
    callback: CallbackQuery, callback_data: DepartmentSelect, state: FSMContext
) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        # bo'lim o'zgarsa, eski brigada endi mos kelmasligi mumkin -- tozalaymiz
        await employee_service.update_employee(
            employee_id, department_id=callback_data.department_id, brigade_id=None
        )
        await state.set_state(None)
        await _refresh_detail(callback, employee_id)
        await callback.answer("Bo'lim yangilandi ✅ (brigada tozalandi)")
    except employee_service.EmployeeNotFoundError:
        await callback.answer("Xodim topilmadi.", show_alert=True)
    except Exception:
        logger.exception("on_edit_department_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.edit_waiting_department, F.data == SKIP)
async def on_edit_department_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        await employee_service.update_employee(employee_id, department_id=None, brigade_id=None)
        await state.set_state(None)
        await _refresh_detail(callback, employee_id)
        await callback.answer("Bo'lim tozalandi ✅")
    except Exception:
        logger.exception("on_edit_department_skipped xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.edit_waiting_brigade, BrigadeSelect.filter())
async def on_edit_brigade_selected(
    callback: CallbackQuery, callback_data: BrigadeSelect, state: FSMContext
) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        await employee_service.update_employee(employee_id, brigade_id=callback_data.brigade_id)
        await state.set_state(None)
        await _refresh_detail(callback, employee_id)
        await callback.answer("Brigada yangilandi ✅")
    except Exception:
        logger.exception("on_edit_brigade_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.edit_waiting_brigade, F.data == SKIP)
async def on_edit_brigade_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        employee_id = data.get("employee_id")
        await employee_service.update_employee(employee_id, brigade_id=None)
        await state.set_state(None)
        await _refresh_detail(callback, employee_id)
        await callback.answer("Brigada tozalandi ✅")
    except Exception:
        logger.exception("on_edit_brigade_skipped xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


# ---------- Qo'shish ----------


@router.callback_query(F.data == EMP_ADD)
async def on_add_requested(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
        await state.set_state(EmployeeManageStates.add_waiting_full_name)
        if callback.message:
            await callback.message.answer("Yangi xodimning to'liq ismini kiriting (bekor qilish: /cancel):")
        await callback.answer()
    except Exception:
        logger.exception("on_add_requested xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.message(EmployeeManageStates.add_waiting_full_name)
async def on_add_full_name_received(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if not full_name:
        await message.answer("Ism bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return

    async with async_session() as session:
        existing = await EmployeeRepository(session).list_by_full_name(full_name)
    if existing:
        await message.answer(f"'{full_name}' ismli xodim allaqachon mavjud. Boshqa ism kiriting yoki /cancel:")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(EmployeeManageStates.add_waiting_phone)
    await message.answer("Telefon raqamini kiriting (masalan: +998901234567):")


@router.message(EmployeeManageStates.add_waiting_phone)
async def on_add_phone_received(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        phone = _validate_phone(text)
    except ValueError as exc:
        await message.answer(f"Noto'g'ri qiymat: {exc}. Qayta kiriting:")
        return

    async with async_session() as session:
        existing = await EmployeeRepository(session).get_by_phone_number(phone)
    if existing is not None:
        await message.answer(f"'{phone}' raqami bilan xodim allaqachon mavjud. Boshqa raqam kiriting yoki /cancel:")
        return

    await state.update_data(phone_number=phone)
    await state.set_state(EmployeeManageStates.add_waiting_role)
    await message.answer("Rolni tanlang:", reply_markup=build_role_keyboard())


@router.callback_query(EmployeeManageStates.add_waiting_role, RoleSelect.filter())
async def on_add_role_selected(callback: CallbackQuery, callback_data: RoleSelect, state: FSMContext) -> None:
    try:
        await state.update_data(role=callback_data.role)
        departments = await _list_all_departments()
        await state.set_state(EmployeeManageStates.add_waiting_department)
        if callback.message:
            await callback.message.edit_text(
                "Bo'limni tanlang:", reply_markup=build_department_keyboard(departments, include_skip=True)
            )
        await callback.answer()
    except Exception:
        logger.exception("on_add_role_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.add_waiting_department, DepartmentSelect.filter())
async def on_add_department_selected(
    callback: CallbackQuery, callback_data: DepartmentSelect, state: FSMContext
) -> None:
    try:
        await state.update_data(department_id=callback_data.department_id)
        brigades = await _list_brigades_for_department(callback_data.department_id)
        await state.set_state(EmployeeManageStates.add_waiting_brigade)
        if callback.message:
            await callback.message.edit_text("Brigadani tanlang:", reply_markup=build_brigade_keyboard(brigades))
        await callback.answer()
    except Exception:
        logger.exception("on_add_department_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.add_waiting_department, F.data == SKIP)
async def on_add_department_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.update_data(department_id=None, brigade_id=None)
        await _show_add_confirmation(callback, state)
        await callback.answer()
    except Exception:
        logger.exception("on_add_department_skipped xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.add_waiting_brigade, BrigadeSelect.filter())
async def on_add_brigade_selected(
    callback: CallbackQuery, callback_data: BrigadeSelect, state: FSMContext
) -> None:
    try:
        await state.update_data(brigade_id=callback_data.brigade_id)
        await _show_add_confirmation(callback, state)
        await callback.answer()
    except Exception:
        logger.exception("on_add_brigade_selected xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


@router.callback_query(EmployeeManageStates.add_waiting_brigade, F.data == SKIP)
async def on_add_brigade_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.update_data(brigade_id=None)
        await _show_add_confirmation(callback, state)
        await callback.answer()
    except Exception:
        logger.exception("on_add_brigade_skipped xatosi")
        await callback.answer("Kutilmagan xatolik yuz berdi.", show_alert=True)


async def _show_add_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(EmployeeManageStates.add_confirming)

    department_name = "-"
    brigade_name = "-"
    async with async_session() as session:
        if data.get("department_id"):
            department = await DepartmentRepository(session).get_by_id(data["department_id"])
            department_name = department.name if department else "-"
        if data.get("brigade_id"):
            brigade = await BrigadeRepository(session).get_by_id(data["brigade_id"])
            brigade_name = brigade.name if brigade else "-"

    role_label = ROLE_LABELS.get(Role(data["role"]), data["role"])
    text = (
        "Yangi xodimni tasdiqlang:\n\n"
        f"Ism: {data['full_name']}\n"
        f"Telefon: {data['phone_number']}\n"
        f"Rol: {role_label}\n"
        f"Bo'lim: {department_name}\n"
        f"Brigada: {brigade_name}"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_yes_no_keyboard())


@router.callback_query(EmployeeManageStates.add_confirming, F.data == CANCEL)
async def on_add_cancelled(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Xodim qo'shish bekor qilindi.")
    await callback.answer()


@router.callback_query(EmployeeManageStates.add_confirming, F.data == CONFIRM)
async def on_add_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    try:
        employee = await employee_service.create_employee(
            full_name=data["full_name"],
            phone_number=data["phone_number"],
            role=Role(data["role"]),
            department_id=data.get("department_id"),
            brigade_id=data.get("brigade_id"),
        )
    except employee_service.DuplicateNameError as exc:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(f"Xatolik: {exc}")
        return
    except employee_service.DuplicatePhoneError as exc:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(f"Xatolik: {exc}")
        return
    except Exception:
        logger.exception("on_add_confirmed xatosi")
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Kutilmagan xatolik yuz berdi.")
        return

    await callback.answer("Xodim qo'shildi ✅")
    text = await _format_employee_detail(employee)
    if callback.message:
        await callback.message.edit_text(
            f"✅ Xodim qo'shildi!\n\n{text}", reply_markup=build_employee_detail_keyboard(employee)
        )
