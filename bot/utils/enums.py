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
