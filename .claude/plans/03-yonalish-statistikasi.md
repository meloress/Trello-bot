# Bo'lim (yo'nalish) bo'yicha statistika kesimi

Holat: ANIQLANGAN BO'SHLIQ — rejalashtirilgan, hali kod yozilmagan.

TZ manbasi: 10.1-band, "Kesim" jadvali to'rtta qatordan iborat: Ishchi
bo'yicha, Brigada/brigadir bo'yicha, **Yo'nalish (board) bo'yicha: "Nechta
faol, nechta kechikkan, nechta 'stop'dagi vazifa"**, Vazifalar bo'yicha
(9-band topshiriqlar statistikasi, ishlab chiqarish statistikasiga
bog'langan holda).

## Nima yo'q (2026-07-17 audit natijasi)

`bot/services/stats_service.py`da xodim (`get_monthly_stats`,
`get_daily_stats`, `get_weekly_stats`, `get_employee_weekly_stats`) va
brigada (`get_brigade_monthly_stats`) kesimlari bor — **bo'lim (department)
darajasidagi kesim umuman yo'q** (`grep department` — hech qanday moslik).
`web/src/routes/stats.js`da ham yo'q. "Vazifalar bo'yicha" (ORDER vs MISC)
alohida ko'rsatkich sifatida ham hech qayerda ajratilmagan — ikkalasi bir
xil umumiy ballarga qo'shilib ketadi (bu 9-band "minus ball xuddi shu
qoidada yoziladi" talabini qanoatlantiradi, lekin "alohida ko'rsatkich"
talabini yo'q).

## Reja

### 1. `stats_service.py`ga yangi funksiya

```python
@dataclass
class DepartmentStats:
    department_id: int
    department_name: str
    active_count: int
    overdue_count: int
    stopped_count: int
    pending_setup_count: int


async def get_department_stats() -> list[DepartmentStats]:
    """10.1-band: yo'nalish (board) bo'yicha — nechta faol, kechikkan,
    stopdagi vazifa. Faqat ORDER turi (MISC'da bo'lim yo'q)."""
    async with async_session() as session:
        departments = await DepartmentRepository(session).list_all()
        tasks = await TaskRepository(session).list_all()

    open_tasks = [t for t in tasks if t.task_type == TaskType.ORDER and t.status != TaskStatus.COMPLETED]
    by_department: dict[int, list[Task]] = defaultdict(list)
    for t in open_tasks:
        if t.current_department_id is not None:
            by_department[t.current_department_id].append(t)

    result = []
    for dept in departments:
        dept_tasks = by_department.get(dept.id, [])
        result.append(DepartmentStats(
            department_id=dept.id,
            department_name=dept.name,
            active_count=sum(1 for t in dept_tasks if t.status == TaskStatus.ACTIVE),
            overdue_count=sum(1 for t in dept_tasks if t.status == TaskStatus.OVERDUE),
            stopped_count=sum(1 for t in dept_tasks if t.status == TaskStatus.STOPPED),
            pending_setup_count=sum(1 for t in dept_tasks if t.status == TaskStatus.PENDING_SETUP),
        ))
    return result
```

Python darajasida guruhlash (SQL `GROUP BY` emas) — loyihaning hozirgi
ko'lami (bir nechta o'nlab ochiq vazifa) uchun yetarli, `_compute_stats()`
allaqachon shu yondashuvni ishlatadi (butun ro'yxatni olib, Python'da
filtrlaydi) — bir xil konvensiya.

### 2. "Vazifalar bo'yicha" (ORDER vs MISC) — mavjud xodim statistikasiga
qo'shimcha ustun

`EmployeeStats`ga ikkita yangi maydon: `order_completed_count`,
`misc_completed_count` (hozirgi `completed_tasks` ikkalasini yig'ib
beradi, buzilmaydi — faqat qo'shimcha breakdown).

### 3. Ko'rsatish

- **Bot**: `/stats` buyrug'iga ikkinchi bo'lim sifatida (bitta xabarda,
  yangi buyruq shart emas) yoki alohida `/bolimstats` — ikkalasi ham
  oqilona, kichik farq. Tavsiya: mavjud `/stats` xabariga qo'shib yuborish
  (bitta joyda hammasi, "bitta oyna" printsipiga mos — 4.1-band).
- **Web**: `web/src/routes/stats.js`ga yangi `GET /api/stats/departments`
  route (bir xil SQL/mantiq Python bilan qo'lda takrorlanadi — mavjud
  konvensiya, CLAUDE.mdda yozilgan) + `public/js/app.js`ga jadval bo'limi
  (yangi karta/bo'lim, mavjud dashboard tuzilishini buzmasdan).

## Tekshirish rejasi

`bot/_smoke_department_stats.py`: bir nechta bo'limda turli holatdagi
(ACTIVE/OVERDUE/STOPPED) sun'iy vazifalar yaratib, `get_department_stats()`
natijasini kutilgan sonlar bilan solishtirish, tozalash.

## Tugagach

- `shared/db-schema.md`ga o'zgarish kerak emas (yangi jadval/ustun yo'q).
- Ushbu hujjat `.claude/plans/`dan olib tashlanadi, README'dagi qator ham.
