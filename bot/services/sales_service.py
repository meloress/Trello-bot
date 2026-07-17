"""13.1/13.2-band: Sotuv CRM — lidlar varonkasi + qo'ng'iroqlar bazasi.
Ishlab chiqarish domenidan (tasks/task_assignments/penalty_service) TO'LIQ
mustaqil (5-bosqich hujjatidagi arxitektura qarori) — o'z jadval to'plami,
o'z servisi.

Trello yozish tartibi `task_service.create_task()` bilan bir xil qoida:
AVVAL Trello'da karta ochiladi/ko'chiriladi, FAQAT shu muvaffaqiyatli
bo'lsagina bazaga yoziladi/yangilanadi."""

import logging
from datetime import datetime, timezone

from config import settings
from core.database import async_session
from db.models.call_log import CallLog
from db.models.lead import Lead
from db.repositories import CallLogRepository, LeadRepository
from services import client_service, settings_service
from trello.client import TrelloClient
from utils.enums import LeadBrand, LeadStage

logger = logging.getLogger(__name__)

# 13.1-band: varonka ILGARI YO'NALISHDA shu tartibda o'tadi. Yopish (won/lost)
# istalgan ochiq bosqichdan mumkin — shu sabab alohida `close_lead()` bor.
_FORWARD_ORDER = [LeadStage.NEW_LEAD, LeadStage.CONTACTED, LeadStage.OFFER_SENT, LeadStage.AGREED]

# TZ 6.1-band: board'da faqat 5 ta list bor (Yangi lid/Aloqa/Taklif/Kelishildi/
# Yopildi) — CLOSED_WON va CLOSED_LOST ikkalasi ham "closed" list'iga tushadi.
_STAGE_TO_LIST_KEY = {
    LeadStage.NEW_LEAD: "new_lead",
    LeadStage.CONTACTED: "contacted",
    LeadStage.OFFER_SENT: "offer_sent",
    LeadStage.AGREED: "agreed",
    LeadStage.CLOSED_WON: "closed",
    LeadStage.CLOSED_LOST: "closed",
}


class LeadNotFoundError(Exception):
    """Berilgan lead_id topilmadi."""


class SalesBoardNotConfiguredError(Exception):
    """Berilgan (brand, bosqich) juftligi uchun Trello list ID
    `app_settings.sales_board_lists`da sozlanmagan."""


class InvalidLeadStateError(Exception):
    """So'ralgan amal lidning joriy bosqichiga mos kelmaydi."""


async def _resolve_list_id(brand: LeadBrand, stage: LeadStage) -> str:
    board_lists = (await settings_service.get_settings()).sales_board_lists
    list_id = board_lists.get(brand.value, {}).get(_STAGE_TO_LIST_KEY[stage])
    if not list_id:
        raise SalesBoardNotConfiguredError(
            f"'{brand.value}' uchun '{stage.value}' bosqichida Trello list sozlanmagan"
        )
    return list_id


async def create_lead(
    *, brand: LeadBrand, client_phone: str, client_full_name: str, seller_id: int
) -> Lead:
    client = await client_service.find_or_create_client(phone_number=client_phone, full_name=client_full_name)
    list_id = await _resolve_list_id(brand, LeadStage.NEW_LEAD)

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        card = await trello.create_card(list_id=list_id, name=client_full_name, desc=f"Tel: {client_phone}")

    now = datetime.now(timezone.utc)
    async with async_session() as session:
        lead = await LeadRepository(session).create(
            client_id=client.id,
            brand=brand,
            stage=LeadStage.NEW_LEAD,
            assigned_seller_id=seller_id,
            trello_card_id=card["id"],
            last_contacted_at=now,
        )
        await session.commit()
        return lead


async def advance_lead_stage(lead_id: int) -> Lead:
    async with async_session() as session:
        repo = LeadRepository(session)
        lead = await repo.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError(f"Lead {lead_id} topilmadi")
        if lead.stage not in _FORWARD_ORDER:
            raise InvalidLeadStateError(f"Lead {lead_id} yopilgan yoki noma'lum bosqichda ({lead.stage})")

        current_index = _FORWARD_ORDER.index(lead.stage)
        if current_index == len(_FORWARD_ORDER) - 1:
            raise InvalidLeadStateError(f"Lead {lead_id} allaqachon so'nggi ochiq bosqichda ({lead.stage})")
        next_stage = _FORWARD_ORDER[current_index + 1]
        brand = lead.brand
        card_id = lead.trello_card_id

    list_id = await _resolve_list_id(brand, next_stage)
    if card_id:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card_id, list_id)

    async with async_session() as session:
        repo = LeadRepository(session)
        lead = await repo.get_by_id(lead_id)
        await repo.update(lead, stage=next_stage)
        await session.commit()
        return lead


async def close_lead(lead_id: int, *, won: bool) -> Lead:
    async with async_session() as session:
        repo = LeadRepository(session)
        lead = await repo.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError(f"Lead {lead_id} topilmadi")
        if lead.stage in (LeadStage.CLOSED_WON, LeadStage.CLOSED_LOST):
            raise InvalidLeadStateError(f"Lead {lead_id} allaqachon yopilgan ({lead.stage})")
        brand = lead.brand
        card_id = lead.trello_card_id

    target_stage = LeadStage.CLOSED_WON if won else LeadStage.CLOSED_LOST
    list_id = await _resolve_list_id(brand, target_stage)
    if card_id:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            await trello.move_card_to_list(card_id, list_id)

    async with async_session() as session:
        repo = LeadRepository(session)
        lead = await repo.get_by_id(lead_id)
        await repo.update(lead, stage=target_stage)
        await session.commit()
        return lead


async def add_call_log(
    lead_id: int, recorded_by_id: int, *, content: str | None, audio_file_id: str | None
) -> CallLog:
    """13.2-band. `content`/`audio_file_id`dan kamida bittasi bo'lishi
    kerak — bo'sh qo'ng'iroq yozuvi ma'nosiz."""
    if not content and not audio_file_id:
        raise ValueError("Qo'ng'iroq matni yoki ovozli xabardan kamida bittasi kerak")

    now = datetime.now(timezone.utc)
    async with async_session() as session:
        lead_repo = LeadRepository(session)
        lead = await lead_repo.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError(f"Lead {lead_id} topilmadi")

        call_log = await CallLogRepository(session).create(
            lead_id=lead_id,
            recorded_by_id=recorded_by_id,
            content=content,
            audio_file_id=audio_file_id,
            called_at=now,
        )
        await lead_repo.update(lead, last_contacted_at=now)
        await session.commit()
        return call_log
