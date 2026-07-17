# MISC vazifalarning hammaga ochiq ro'yxati

Holat: ANIQLANGAN BO'SHLIQ — rejalashtirilgan, hali kod yozilmagan.

TZ manbasi: 9-band, aniq matn: *"Vazifa HAMMAGA ko'rinadi (ochiq ro'yxat,
hamma o'qiy oladi), lekin signal faqat belgilanganlarga boradi."*

## Nima bor (2026-07-17 audit natijasi)

`bot/handlers/worker/tasks.py:cmd_tasks()` (`/tasks`) — faqat so'ragan
xodimga BIRIKTIRILGAN vazifalarni ko'rsatadi (`_list_my_tasks`,
`TaskAssignmentRepository.list_by_employee` orqali). Bu — "Mening
buyurtmalarim/vazifalarim" (11-band) uchun to'g'ri, lekin 9-bandning
"hammaga ochiq ro'yxat" qismini qamramaydi — HAMMA MISC topshiriqlarni
(kim biriktirilganidan qat'iy nazar) ko'radigan alohida ro'yxat yo'q.

## Reja

### 1. Yangi buyruq: `/vazifalar` (`handlers/worker/tasks.py`, bir xil
routerga qo'shiladi — bu router hech qanday `RoleAccessMiddleware`ga ega
emas, ya'ni har qanday ro'yxatdan o'tgan xodim uchun ochiq, aynan TZ
talab qilgan "hammaga ko'rinadi" xususiyatiga mos)

```python
@router.message(Command("vazifalar"))
async def cmd_all_misc_tasks(message: Message) -> None:
    """9-band: "Vazifa HAMMAGA ko'rinadi" — kim biriktirilganidan qat'iy
    nazar, barcha ochiq MISC topshiriqlar ro'yxati (o'qish uchun, amal
    qilish tugmalarisiz — signal faqat biriktirilganlarga boradi, bu yerda
    faqat ko'rish)."""
    try:
        async with async_session() as session:
            tasks = await TaskRepository(session).list_all()
            open_misc = [t for t in tasks if t.task_type == TaskType.MISC and t.status != TaskStatus.COMPLETED]

            employee_repo = EmployeeRepository(session)
            assignment_repo = TaskAssignmentRepository(session)
            lines = ["📋 Barcha ochiq topshiriqlar:", ""]
            for task in open_misc:
                assignees = await assignment_repo.list_by_task(task.id)
                names = []
                for a in assignees:
                    emp = await employee_repo.get_by_id(a.employee_id)
                    if emp:
                        names.append(emp.full_name)
                label = _STATUS_LABELS.get(task.status, str(task.status))
                lines.append(f"• {task.title} — {label} — {', '.join(names) if names else 'kim biriktirilmagan'}")

        if not open_misc:
            await message.answer("Hozircha ochiq topshiriqlar yo'q.")
            return
        await message.answer("\n".join(lines))
    except Exception:
        logger.exception("cmd_all_misc_tasks xatosi (telegram_id=%s)", message.from_user.id)
        await message.answer("Kutilmagan xatolik yuz berdi.")
```

Ataylab **amal tugmalarisiz** (Boshlash/Stop/Yakunlash yo'q) — TZ aniq
ajratadi: "signal faqat belgilanganlarga boradi", ya'ni bu faqat ko'rish
uchun ro'yxat, faqat biriktirilgan xodim o'ziga tegishlisini `/tasks`
orqali boshqaradi. Ikkalasi (`/tasks` va `/vazifalar`) turli maqsadga
xizmat qiladi, biri ikkinchisini almashtirmaydi.

### 2. `TaskRepository`ga yangi metod (ixtiyoriy, optimallashtirish)

Hozirgi reja `list_all()` + Python filtrlashdan foydalanadi (03-hujjatdagi
bo'lim statistikasi bilan bir xil naqsh, loyiha ko'lamiga yetarli). Agar
kelajakda vazifalar soni ko'payib SQL darajasida filtrlash kerak bo'lsa,
`TaskRepository.list_open_misc()` qo'shish mumkin — hozircha shart emas.

## Tekshirish rejasi

`bot/_smoke_open_misc_list.py`: bir nechta MISC vazifa (turli xodimlarga
biriktirilgan) yaratib, boshqa (hech biriga biriktirilmagan uchinchi)
xodim nomidan `/vazifalar` chaqirilganda BARCHASI ko'rinishini tasdiqlash,
tozalash.

## Tugagach

- `shared/db-schema.md`ga o'zgarish kerak emas.
- Ushbu hujjat `.claude/plans/`dan olib tashlanadi, README'dagi qator ham.
