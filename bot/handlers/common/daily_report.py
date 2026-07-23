"""Kunlik rasm/video hisobot muvofiqligi (Fasad sex TZ, Phase 8) — bu
tizimning `/mijoz`dan (`handlers/common/client_link.py`) keyingi IKKINCHI
ataylab chat-only istisnosi: Telegram'ning tabiiy kamera/galereya
biriktirish tugmasi Mini App WebView fayl-inputidan ancha qulay.

Bu FAQAT kuzatuv — hech qanday jarima/ball bilan bog'liq emas
(`penalty_service.py`ga ATAYLAB tegilmagan, TZning o'zi ham bu masalada
ochiq savol qoldirgan).

DIZAYN QARORI — nega STATE emas: `jobs/daily_report_job.py` (kunlik so'rov
yuboruvchi) `main.py`da faqat `Bot` obyektini oladi, `Dispatcher`/uning FSM
`storage`sini OLMAYDI (`reminder_job.py`/`report_job.py` bilan bir xil
naqsh — hech biri FSMContext'ga kirish huquqiga ega emas). Demak job
ixtiyoriy foydalanuvchi uchun "holat"ni oldindan o'rnata olmaydi — buni
qilish uchun `main.py`/job signature'lariga `storage`ni alohida uzatish
kerak bo'lardi, bu yerda ishlatilmagan yangi bog'lanish qo'shgan bo'lardi.
Shu sabab qabul qiluvchi tomon ham STATE'GA BOG'LIQ EMAS: xodim istalgan
vaqtda (so'rovga javoban yoki o'zicha) rasm/video yuborsa, pastdagi filter
uni ushlaydi — agar yuboruvchi `daily_report_required=True` FAOL xodim
bo'lsa. Aks holda filter mos kelmaydi va xabar odatdagidek
`handlers/common/start.py`ning "hammasiga javob"iga tushib ketadi
(`main.py`da bu router O'SHA catch-all'dan OLDIN ro'yxatdan o'tkazilishi
kerak — aks holda catch-all uni ELIDA ushlab qolib, bu yerga umuman
yetib kelmaydi, xuddi `/mijoz` uchun ham amal qiladigan qoida)."""

import logging

from aiogram import Router
from aiogram.types import Message

from core.database import async_session
from db.repositories import EmployeeRepository
from services import daily_report_service

logger = logging.getLogger(__name__)

router = Router(name="common_daily_report")


async def _is_daily_report_sender(message: Message) -> bool | dict:
    """Aiogram filter: bool qaytarsa oddiy true/false, dict qaytarsa shu
    dict handler kwarg'lariga qo'shiladi (`employee`ni ikkinchi marta
    bazadan o'qimaslik uchun)."""
    if not (message.photo or message.video):
        return False
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_telegram_id(message.from_user.id)
    if employee is None or not employee.is_active or not employee.daily_report_required:
        return False
    return {"daily_report_employee": employee}


@router.message(_is_daily_report_sender)
async def on_daily_report_media(message: Message, daily_report_employee) -> None:
    file_id = message.video.file_id if message.video else message.photo[-1].file_id
    try:
        await daily_report_service.submit_daily_report(daily_report_employee.id, file_id)
    except Exception:
        logger.exception(
            "submit_daily_report xatosi (employee_id=%s)", daily_report_employee.id
        )
        await message.answer("Kutilmagan xatolik yuz berdi.")
        return

    logger.info(
        "Kunlik hisobot qabul qilindi: employee_id=%s", daily_report_employee.id
    )
    await message.answer("✅ Bugungi hisobot qabul qilindi. Rahmat!")
