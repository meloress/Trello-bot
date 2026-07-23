from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    BRIGADIER = "brigadier"
    WORKER = "worker"
    SELLER = "seller"
    OBSERVER = "observer"


class TaskStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    STOPPED = "stopped"
    PENDING_SETUP = "pending_setup"


class TaskType(str, Enum):
    """9-band: ORDER — Trello bilan bog'liq asosiy buyurtma; MISC — Trello'siz,
    faqat tizim ichida boshqariladigan alohida topshiriq."""

    ORDER = "order"
    MISC = "misc"


class ReminderUrgency(str, Enum):
    """7.3-band: kunlik eslatma jadvalidagi har bir vaqt o'zining
    eskalatsiya darajasiga ega (xabar matni shunga qarab kuchayadi)."""

    INFO = "info"
    WARNING = "warning"
    URGENT = "urgent"


class FinancialSuggestionKind(str, Enum):
    """8.6-band: ikkita mustaqil moliyaviy qoida — bittasi xodim ish haqidan
    ushlab qolish, ikkinchisi mijozdan avans kechirimi."""

    WAGE_DEDUCTION = "wage_deduction"
    ADVANCE_WAIVER = "advance_waiver"
    # Fasad sex TZ, Phase 7: bosqich necha kunda tugatilganiga qarab tavsiya
    # etiladigan to'lov (tezlik darajasi bo'yicha) — kelib chiqishi boshqa
    # ikkitasidan farqli (jarima/kechirim emas, mumkin bo'lgan BONUS).
    SPEED_TIER_BONUS = "speed_tier_bonus"


class FinancialSuggestionStatus(str, Enum):
    """8.6-band: tizim faqat TAKLIF yozadi (`PENDING_MANAGER_REVIEW`) —
    tasdiqlash/rad etish INSON tomonidan, boshqa modulda amalga oshiriladi."""

    PENDING_MANAGER_REVIEW = "pending_manager_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class LeadBrand(str, Enum):
    """6.1-band: ikkita mustaqil sotuv yo'nalishi — har biri o'z Trello
    board'iga ega (Ezza sotuv / Melores Mebel sotuv)."""

    EZZA = "ezza"
    MELORES = "melores"


class LeadStage(str, Enum):
    """13.1-band varonka bosqichlari. CLOSED_WON/CLOSED_LOST ikkalasi ham
    Trello'da bitta "Yopildi" list'iga tushadi (TZ 6.1-band board'da faqat
    5 ta list bor) — g'alaba/yo'qotish farqi faqat shu ustunda saqlanadi."""

    NEW_LEAD = "new_lead"
    CONTACTED = "contacted"
    OFFER_SENT = "offer_sent"
    AGREED = "agreed"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
