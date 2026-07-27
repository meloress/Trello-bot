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


class MiscCategory(str, Enum):
    """Fasad sex TZ, Phase 9: MISC vazifalar uchun ixtiyoriy kategoriya
    belgisi (ofis/Fasad sex ishlab chiqarish/o'rnatuvchilar/payvandchilar) —
    faqat ichki barqaror identifikator, aniq o'zbekcha nomlanish hali ochiq
    savol (`.claude/plans/09z-fasad-sex-ochiq-savollar.md` #6/#14)."""

    OFFICE = "office"
    FASAD_SEX = "fasad_sex"
    INSTALLER = "installer"
    WELDER = "welder"


class ReminderUrgency(str, Enum):
    """7.3-band: kunlik eslatma jadvalidagi har bir vaqt o'zining
    eskalatsiya darajasiga ega (xabar matni shunga qarab kuchayadi)."""

    INFO = "info"
    WARNING = "warning"
    URGENT = "urgent"


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


class ClaimActionType(str, Enum):
    """Ishchi Mini App'da qaysi tugmani bosgani — tasdiqlanmaguncha
    haqiqiy TaskStatus o'zgarishiga sabab bo'lmaydi."""

    PAUSE = "pause"
    FINISH = "finish"


class ClaimStatus(str, Enum):
    """Rahbar (SUPERVISOR/ADMIN) tasdiqlagunga qadar so'rov PENDING holatida
    turadi — faqat shu payt haqiqiy tasks/StopLog yozuvi yaratiladi."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
