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
    # Davom ettirish ham rahbar tasdig'ini talab qiladi (Pauza/Yakunlash bilan
    # bir xil qoida) — ilgari brigadir bosishi bilan darhol ishlar edi.
    RESUME = "resume"


class ClaimStatus(str, Enum):
    """Rahbar (SUPERVISOR/ADMIN) tasdiqlagunga qadar so'rov PENDING holatida
    turadi — faqat shu payt haqiqiy tasks/StopLog yozuvi yaratiladi."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TrelloListKind(str, Enum):
    """Mebel moduli: kuzatilayotgan Trello ro'yxati NIMA ma'noni bildiradi.

    Haqiqiy "Fasad seh" boardida bitta bosqichga (masalan Shpon) bir nechta
    ro'yxat to'g'ri keladi — har bir brigadaning o'z ro'yxati bor, ustiga
    yana "hali boshlanmadik" kabi kutish ro'yxatlari. Shu sabab bo'lim <->
    ro'yxat bog'lanishi 1:1 emas, 1:N (`department_trello_lists`), va har bir
    ro'yxat qaysi turga kirishi shu yerda belgilanadi.

    WORK  — brigadaning ish ro'yxati. Karta bu yerga tushdi = ish BOSHLANDI:
            vazifa ochiladi, kartadagi ishchilarga xabar boradi, taymer ketadi.
    QUEUE — kutish/o'tish ro'yxati ("shpon hali boshlanmadik", "shkurka hali
            tasdiqlanmadi", shuningdek kraskadan keyingi dastavka/ustanovka).
            Karta bu yerda TURSA hech qanday vazifa ochilmaydi; agar shu karta
            uchun ochiq vazifa bo'lsa — demak u ish ro'yxatidan CHIQIB ketgan,
            ya'ni o'sha bosqich tugagan: vazifa avtomatik yakunlanadi.
    """

    WORK = "work"
    QUEUE = "queue"
