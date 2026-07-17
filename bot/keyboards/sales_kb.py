from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models.lead import Lead
from utils.enums import LeadBrand

BRAND_LABELS: dict[LeadBrand, str] = {
    LeadBrand.EZZA: "Ezza",
    LeadBrand.MELORES: "Melores Mebel",
}

STAGE_LABELS: dict[str, str] = {
    "new_lead": "🆕 Yangi lid",
    "contacted": "📞 Aloqa qilindi",
    "offer_sent": "📄 Taklif berildi",
    "agreed": "🤝 Kelishildi",
    "closed_won": "✅ Yopildi (g'alaba)",
    "closed_lost": "❌ Yopildi (bekor)",
}


class BrandSelect(CallbackData, prefix="leadbrand"):
    brand: str


class LeadSelect(CallbackData, prefix="leadsel"):
    lead_id: int


class LeadAdvance(CallbackData, prefix="leadadv"):
    lead_id: int


class LeadClose(CallbackData, prefix="leadclose"):
    lead_id: int
    won: bool


class LeadCallLogStart(CallbackData, prefix="leadcall"):
    lead_id: int


def build_brand_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=BrandSelect(brand=brand.value).pack())]
        for brand, label in BRAND_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_lead_list_keyboard(leads: list[Lead]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{STAGE_LABELS.get(lead.stage.value, lead.stage.value)} — lead #{lead.id}",
                callback_data=LeadSelect(lead_id=lead.id).pack(),
            )
        ]
        for lead in leads
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_lead_detail_keyboard(lead: Lead) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📞 Qo'ng'iroq qo'shish", callback_data=LeadCallLogStart(lead_id=lead.id).pack())]
    ]
    if lead.stage.value in ("new_lead", "contacted", "offer_sent"):
        rows.append(
            [InlineKeyboardButton(text="➡️ Keyingi bosqich", callback_data=LeadAdvance(lead_id=lead.id).pack())]
        )
    if lead.stage.value not in ("closed_won", "closed_lost"):
        rows.append([
            InlineKeyboardButton(text="✅ Yopish (g'alaba)", callback_data=LeadClose(lead_id=lead.id, won=True).pack()),
            InlineKeyboardButton(text="❌ Yopish (bekor)", callback_data=LeadClose(lead_id=lead.id, won=False).pack()),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
