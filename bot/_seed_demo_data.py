"""Demo ma'lumotlar generatori — boshliqqa ko'rsatish uchun.

Bo'sh Railway DB'ni real servis funksiyalari orqali (task_service,
timer_service, penalty_service, sales_service, financial_service,
client_service) to'ldiradi — natijada Trello'da HAQIQIY kartalar/
checklist/ranglar paydo bo'ladi, DB va Trello bir-biriga to'liq mos keladi.

Boshqa `_smoke_*.py` skriptlaridan farqli o'laroq, bu skript ISHLATILGACH
O'CHIRILMAYDI — demo holatini istalgan payt qayta generatsiya qilish uchun
saqlanadi. Ikkinchi marta ishga tushirilsa, xodim/mijoz ismlari/telefonlari
allaqachon mavjudligi sababli xato beradi — qayta ishlatish uchun avval
demo qatorlarini bazadan tozalash kerak.

Butunlay YANGI Trello board yaratadi ("Melores Mebel — DEMO") — mavjud
"Test"/"Fasad seh"/"nazorat trello" board'lariga HECH QACHON tegmaydi.

Ishga tushirish: cd bot && .venv\\Scripts\\python _seed_demo_data.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

from config import settings
from core.database import async_session
from db.repositories import BrigadeRepository, DepartmentRepository, TaskRepository
from services import (
    client_service,
    employee_service,
    financial_service,
    penalty_service,
    sales_service,
    settings_service,
    task_service,
    timer_service,
)
from trello.client import TrelloClient
from utils.enums import LeadBrand, Role, TaskStatus

ADMIN_NAMES = ["Og'abek Jumayev", "Habibulla Yusupkho'jayev"]

BRIGADE_DEPT = {
    "brig_s1": "dept_stolyar",
    "brig_s2": "dept_stolyar",
    "brig_shk": "dept_shkurka",
    "brig_kr": "dept_kraska",
}

_phone_counter = 0
_client_phone_counter = 0


def _next_phone() -> str:
    global _phone_counter
    _phone_counter += 1
    return f"+998901{_phone_counter:06d}"


def _client_phone() -> str:
    global _client_phone_counter
    _client_phone_counter += 1
    return f"+998907{_client_phone_counter:06d}"


async def create_demo_board() -> dict[str, str]:
    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        board = await trello.create_board("Melores Mebel — DEMO")
        board_id = board["id"]
        print(f"Trello board yaratildi: {board['name']} ({board_id})")

        list_names = [
            "Stolyar", "Shkurka", "Kraska",
            "EZZA: Yangi lid", "EZZA: Aloqa qilindi", "EZZA: Taklif berildi",
            "EZZA: Kelishildi", "EZZA: Yopildi",
            "MELORES: Yangi lid", "MELORES: Aloqa qilindi", "MELORES: Taklif berildi",
            "MELORES: Kelishildi", "MELORES: Yopildi",
        ]
        list_ids: dict[str, str] = {}
        for name in list_names:
            trello_list = await trello.create_list(board_id, name)
            list_ids[name] = trello_list["id"]
            print(f"  list: {name} ({trello_list['id']})")
        return list_ids


async def create_org_structure(list_ids: dict[str, str]) -> dict:
    async with async_session() as session:
        dept_repo = DepartmentRepository(session)
        brigade_repo = BrigadeRepository(session)

        dept_stolyar = await dept_repo.create(
            name="Stolyar", trello_list_id=list_ids["Stolyar"], auto_reassign_after_48h=True
        )
        dept_shkurka = await dept_repo.create(name="Shkurka", trello_list_id=list_ids["Shkurka"])
        dept_kraska = await dept_repo.create(name="Kraska", trello_list_id=list_ids["Kraska"])
        await session.flush()

        await dept_repo.update(dept_stolyar, next_department_id=dept_shkurka.id)
        await dept_repo.update(dept_shkurka, next_department_id=dept_kraska.id)

        brig_s1 = await brigade_repo.create(name="1-brigada (Stolyar)", department_id=dept_stolyar.id)
        brig_s2 = await brigade_repo.create(name="2-brigada (Stolyar)", department_id=dept_stolyar.id)
        brig_shk = await brigade_repo.create(name="1-brigada (Shkurka)", department_id=dept_shkurka.id)
        brig_kr = await brigade_repo.create(name="1-brigada (Kraska)", department_id=dept_kraska.id)

        await session.commit()
        print(f"Bo'limlar: Stolyar #{dept_stolyar.id} -> Shkurka #{dept_shkurka.id} -> Kraska #{dept_kraska.id}")
        print(f"Brigadalar: s1=#{brig_s1.id} s2=#{brig_s2.id} shk=#{brig_shk.id} kr=#{brig_kr.id}")

        return {
            "dept_stolyar": dept_stolyar.id,
            "dept_shkurka": dept_shkurka.id,
            "dept_kraska": dept_kraska.id,
            "brig_s1": brig_s1.id,
            "brig_s2": brig_s2.id,
            "brig_shk": brig_shk.id,
            "brig_kr": brig_kr.id,
        }


async def create_employees(org: dict) -> dict:
    employees: dict = {}

    for name in ADMIN_NAMES:
        emp = await employee_service.create_employee(full_name=name, phone_number=_next_phone(), role=Role.ADMIN)
        employees[name] = emp.id
        print(f"ADMIN: {name} (#{emp.id})")

    supervisor = await employee_service.create_employee(
        full_name="Jamshid Aka", phone_number=_next_phone(), role=Role.SUPERVISOR, department_id=org["dept_stolyar"]
    )
    employees["supervisor"] = supervisor.id
    print(f"SUPERVISOR: Jamshid Aka (#{supervisor.id})")

    brigade_defs = [
        ("brig_s1", "Ilhom Brigadirov", ["Sardor Aliyev", "Bekzod Qodirov"]),
        ("brig_s2", "Davron Rashidov", ["Aziz Tursunov", "Farrux Nabiyev"]),
        ("brig_shk", "Elyor Mahmudov", ["G'olib Yusupov", "Hasan Rustamov"]),
        ("brig_kr", "Jasur Toshpulatov", ["Sherzod Yoqubov", "Ravshan Ergashev"]),
    ]

    async with async_session() as session:
        brigade_repo = BrigadeRepository(session)
        for brig_key, brigadier_name, worker_names in brigade_defs:
            dept_key = BRIGADE_DEPT[brig_key]
            brigadier = await employee_service.create_employee(
                full_name=brigadier_name,
                phone_number=_next_phone(),
                role=Role.BRIGADIER,
                department_id=org[dept_key],
                brigade_id=org[brig_key],
            )
            employees[brig_key + "_brigadier"] = brigadier.id
            brigade_row = await brigade_repo.get_by_id(org[brig_key])
            await brigade_repo.update(brigade_row, brigadier_id=brigadier.id)

            worker_ids = []
            for worker_name in worker_names:
                worker = await employee_service.create_employee(
                    full_name=worker_name,
                    phone_number=_next_phone(),
                    role=Role.WORKER,
                    department_id=org[dept_key],
                    brigade_id=org[brig_key],
                )
                worker_ids.append(worker.id)
            employees[brig_key + "_workers"] = worker_ids
            print(f"Brigada {brig_key}: brigadir {brigadier_name} (#{brigadier.id}), ishchilar {worker_names} {worker_ids}")
        await session.commit()

    sellers = {}
    for brand_key, name in [("ezza", "Nilufar Sodiqova"), ("melores", "Kamola Otabekova")]:
        seller = await employee_service.create_employee(full_name=name, phone_number=_next_phone(), role=Role.SELLER)
        sellers[brand_key] = seller.id
        print(f"SELLER ({brand_key}): {name} (#{seller.id})")
    employees["sellers"] = sellers

    return employees


async def create_clients() -> dict:
    clients = {}
    for key, name in [
        ("client_a", "Bahodir Ismoilov"),
        ("client_b", "Malika Rahimova"),
        ("client_c", "Otabek Yunusov"),
    ]:
        client = await client_service.find_or_create_client(phone_number=_client_phone(), full_name=name)
        clients[key] = client.id
        print(f"Mijoz: {name} (#{client.id})")
    return clients


async def create_production_tasks(org: dict, employees: dict, clients: dict) -> dict:
    now = datetime.now(timezone.utc)
    tasks_info: dict = {}

    def workers_for(brig_key: str) -> list[int]:
        return employees[brig_key + "_workers"]

    def dept_for(brig_key: str) -> int:
        return org[BRIGADE_DEPT[brig_key]]

    # 1) Muddatidan oldin yakunlangan (plus ball)
    plus_ball_tasks = []
    for i, (hours, brig_key) in enumerate(
        zip([48, 60, 72, 50, 55], ["brig_s1", "brig_s2", "brig_shk", "brig_kr", "brig_s1"])
    ):
        task = await task_service.create_task(
            title=f"Buyurtma #{100 + i} — muddatidan oldin bajarildi",
            description="Demo: sifatli va tez bajarilgan ish",
            deadline=now + timedelta(hours=hours),
            department_id=dept_for(brig_key),
            employee_ids=workers_for(brig_key),
            client_id=clients["client_a"] if i == 0 else None,
        )
        await timer_service.finish_task(task.id)
        kpi = await penalty_service.calculate_and_apply_task_penalty(task.id)
        plus_ball_tasks.append(task.id)
        print(f"  [plus-ball] Task #{task.id} ({hours}h oldin): {len(kpi)} KPI yozuvi")
    tasks_info["plus_ball"] = plus_ball_tasks

    # 2) Turli darajada kechikkan (24-48/48-72/72-96/96-120 soat bracketlari)
    late_tasks = []
    for i, (hours, brig_key) in enumerate(
        zip([26, 40, 55, 80, 105], ["brig_s2", "brig_shk", "brig_kr", "brig_s1", "brig_shk"])
    ):
        task = await task_service.create_task(
            title=f"Buyurtma #{200 + i} — {hours} soat kechikkan",
            description="Demo: kechikish jarima namunasi",
            deadline=now - timedelta(hours=hours),
            department_id=dept_for(brig_key),
            employee_ids=workers_for(brig_key),
            client_id=clients["client_b"] if i == 0 else None,
        )
        await timer_service.finish_task(task.id)
        kpi = await penalty_service.calculate_and_apply_task_penalty(task.id)
        late_tasks.append(task.id)
        print(f"  [late] Task #{task.id} ({hours}h kech): {len(kpi)} KPI yozuvi")
    tasks_info["late"] = late_tasks

    # 3) To'liq ko'p bosqichli zanjir: Stolyar -> Shkurka -> Kraska
    full_chain_tasks = []
    for i, brig_key in enumerate(["brig_s1", "brig_s2"]):
        task = await task_service.create_task(
            title=f"Buyurtma #{300 + i} — to'liq zanjir (Stolyar->Shkurka->Kraska)",
            description="Demo: ko'p bosqichli progressiya, checklist to'liq bajariladi",
            deadline=now + timedelta(hours=48),
            department_id=org["dept_stolyar"],
            employee_ids=workers_for(brig_key),
            client_id=clients["client_c"] if i == 0 else None,
        )
        stage1_id = task.id
        await timer_service.finish_task(stage1_id)
        await penalty_service.calculate_and_apply_task_penalty(stage1_id)

        stage2 = await task_service.advance_task_stage(stage1_id)
        stage2 = await task_service.activate_pending_stage(
            stage2.id, deadline=now + timedelta(hours=48), employee_ids=workers_for("brig_shk")
        )
        await timer_service.finish_task(stage2.id)
        await penalty_service.calculate_and_apply_task_penalty(stage2.id)

        stage3 = await task_service.advance_task_stage(stage2.id)
        stage3 = await task_service.activate_pending_stage(
            stage3.id, deadline=now + timedelta(hours=48), employee_ids=workers_for("brig_kr")
        )
        await timer_service.finish_task(stage3.id)
        await penalty_service.calculate_and_apply_task_penalty(stage3.id)

        final = await task_service.advance_task_stage(stage3.id)
        assert final is None, "kutilgan: Kraska zanjirning so'nggi bosqichi"
        full_chain_tasks.append((stage1_id, stage2.id, stage3.id))
        print(f"  [full-chain] {stage1_id} -> {stage2.id} -> {stage3.id} (COMPLETED)")
    tasks_info["full_chain"] = full_chain_tasks

    # 4) Stop holatida qoldiriladi (jonli namoyish uchun)
    stop_task = await task_service.create_task(
        title="Buyurtma #400 — Stop holatida",
        description="Demo: 'Stop' tugmasi namunasi",
        deadline=now + timedelta(hours=48),
        department_id=org["dept_stolyar"],
        employee_ids=workers_for("brig_s1"),
    )
    await timer_service.stop_task(
        stop_task.id, workers_for("brig_s1")[0], "Yog'och materiali yetishmayapti, ombordan kutilmoqda"
    )
    tasks_info["stop"] = stop_task.id
    print(f"  [stop] Task #{stop_task.id} STOPPED holatida qoldirildi")

    # 5) 8.3-band avto-o'tkazish namunasi
    reassign_task = await task_service.create_task(
        title="Buyurtma #500 — 8.3 avto-o'tkazish namunasi",
        description="Demo: 48+ soat kechikkan, brigada almashtirildi",
        deadline=now - timedelta(hours=50),
        department_id=org["dept_stolyar"],
        employee_ids=workers_for("brig_s1"),
    )
    async with async_session() as session:
        task_repo = TaskRepository(session)
        row = await task_repo.get_by_id(reassign_task.id)
        # overdue_watch_job hali chaqirilmagani uchun, real oqimda bu status
        # avtomatik OVERDUE'ga o'tgan bo'lardi -- demo tezligi uchun to'g'ridan
        # to'g'ri o'rnatiladi (reassign_task_brigade OVERDUE holatini talab qiladi).
        await task_repo.update(row, status=TaskStatus.OVERDUE)
        await session.commit()
    reassigned = await task_service.reassign_task_brigade(reassign_task.id, org["brig_s2"])
    tasks_info["reassigned"] = reassigned.id
    print(f"  [8.3-reassign] Task #{reassigned.id}: brig_s1 -> brig_s2 ga o'tkazildi")

    # 6) PENDING_SETUP holatida qoldiriladi (jonli namoyish uchun)
    pending_source = await task_service.create_task(
        title="Buyurtma #600 — 2-bosqich sozlanishi kutilmoqda",
        description="Demo: PENDING_SETUP namunasi",
        deadline=now + timedelta(hours=30),
        department_id=org["dept_stolyar"],
        employee_ids=workers_for("brig_s2"),
    )
    await timer_service.finish_task(pending_source.id)
    await penalty_service.calculate_and_apply_task_penalty(pending_source.id)
    pending_stage2 = await task_service.advance_task_stage(pending_source.id)
    tasks_info["pending_setup"] = pending_stage2.id
    print(f"  [pending-setup] Task #{pending_stage2.id} (Shkurka, sozlanishi kutilmoqda)")

    # 7) Yangi, tegilmagan ACTIVE vazifalar (jonli namoyish uchun)
    fresh_tasks = []
    for i, brig_key in enumerate(["brig_kr", "brig_shk"]):
        task = await task_service.create_task(
            title=f"Buyurtma #{700 + i} — jonli namoyish uchun",
            description="Demo: hali boshlanmagan, jonli ko'rsatish uchun qoldirilgan",
            deadline=now + timedelta(hours=72),
            department_id=dept_for(brig_key),
            employee_ids=workers_for(brig_key),
        )
        fresh_tasks.append(task.id)
    tasks_info["fresh"] = fresh_tasks
    print(f"  [fresh] {fresh_tasks} — ACTIVE holatida, jonli namoyish uchun")

    # 8) MISC vazifalar (9-band)
    misc1 = await task_service.create_misc_task(
        text="Omborni tartibga keltirish",
        deadline=now + timedelta(days=3),
        employee_ids=[employees["supervisor"], workers_for("brig_s1")[0]],
    )
    misc2 = await task_service.create_misc_task(
        text="Yangi mijozlarga qo'ng'iroq qilib, buyurtma holatini so'rash",
        deadline=now + timedelta(days=2),
        employee_ids=[workers_for("brig_shk")[0]],
    )
    tasks_info["misc"] = [misc1.id, misc2.id]
    print(f"  [misc] {tasks_info['misc']}")

    return tasks_info


async def create_financial_demo(org: dict, employees: dict) -> dict:
    now = datetime.now(timezone.utc)

    long_task = await task_service.create_task(
        title="Buyurtma #800 — uzoq turgan bosqich",
        description="Demo: moliyaviy bayroqlash (8.6-band 1-qoida)",
        deadline=now + timedelta(days=10),
        department_id=org["dept_shkurka"],
        employee_ids=employees["brig_shk_workers"],
    )
    async with async_session() as session:
        task_repo = TaskRepository(session)
        row = await task_repo.get_by_id(long_task.id)
        await task_repo.update(row, started_at=now - timedelta(days=6))
        await session.commit()
    suggestion1 = await financial_service.flag_long_duration_stage(long_task.id)
    print(f"  [moliyaviy-1] Task #{long_task.id}: taklif #{suggestion1.id if suggestion1 else None}")

    advance_task = await task_service.create_task(
        title="Buyurtma #801 — avans kechirimi namunasi",
        description="Demo: moliyaviy bayroqlash (8.6-band 2-qoida)",
        deadline=now - timedelta(hours=30),
        department_id=org["dept_kraska"],
        employee_ids=employees["brig_kr_workers"],
    )
    await timer_service.finish_task(advance_task.id)
    await penalty_service.calculate_and_apply_task_penalty(advance_task.id)
    suggestion2 = await financial_service.create_advance_waiver_suggestion(
        advance_task.id, advance_percent_paid=85, is_late=True, order_total_value=25_000_000
    )
    print(f"  [moliyaviy-2] Task #{advance_task.id}: taklif #{suggestion2.id}")

    return {"wage_deduction_task": long_task.id, "advance_waiver_task": advance_task.id}


async def create_sales_demo(list_ids: dict[str, str], employees: dict) -> list[int]:
    await settings_service.update_setting(
        sales_board_lists={
            "ezza": {
                "new_lead": list_ids["EZZA: Yangi lid"],
                "contacted": list_ids["EZZA: Aloqa qilindi"],
                "offer_sent": list_ids["EZZA: Taklif berildi"],
                "agreed": list_ids["EZZA: Kelishildi"],
                "closed": list_ids["EZZA: Yopildi"],
            },
            "melores": {
                "new_lead": list_ids["MELORES: Yangi lid"],
                "contacted": list_ids["MELORES: Aloqa qilindi"],
                "offer_sent": list_ids["MELORES: Taklif berildi"],
                "agreed": list_ids["MELORES: Kelishildi"],
                "closed": list_ids["MELORES: Yopildi"],
            },
        }
    )

    seller_ezza = employees["sellers"]["ezza"]
    seller_melores = employees["sellers"]["melores"]

    lead1 = await sales_service.create_lead(
        brand=LeadBrand.EZZA, client_phone=_client_phone(), client_full_name="Sarvar Xolmatov", seller_id=seller_ezza
    )
    lead2 = await sales_service.create_lead(
        brand=LeadBrand.EZZA, client_phone=_client_phone(), client_full_name="Zarina Ne'matova", seller_id=seller_ezza
    )
    lead2 = await sales_service.advance_lead_stage(lead2.id)
    lead3 = await sales_service.create_lead(
        brand=LeadBrand.EZZA, client_phone=_client_phone(), client_full_name="Ulug'bek Sattorov", seller_id=seller_ezza
    )
    lead3 = await sales_service.advance_lead_stage(lead3.id)
    lead3 = await sales_service.advance_lead_stage(lead3.id)
    lead3 = await sales_service.close_lead(lead3.id, won=True)

    lead4 = await sales_service.create_lead(
        brand=LeadBrand.MELORES, client_phone=_client_phone(), client_full_name="Dilshod Yormatov", seller_id=seller_melores
    )
    lead5 = await sales_service.create_lead(
        brand=LeadBrand.MELORES, client_phone=_client_phone(), client_full_name="Gulnora Saidova", seller_id=seller_melores
    )
    lead5 = await sales_service.close_lead(lead5.id, won=False)

    await sales_service.add_call_log(
        lead1.id, seller_ezza, content="Birinchi qo'ng'iroq, mijoz qiziqdi, o'lchamlar yuborishni so'radi", audio_file_id=None
    )
    await sales_service.add_call_log(
        lead2.id, seller_ezza, content="Taklif yuborildi, javob kutilmoqda", audio_file_id=None
    )

    lead_ids = [lead1.id, lead2.id, lead3.id, lead4.id, lead5.id]
    print(f"  Lidlar: {lead_ids}")
    return lead_ids


async def main() -> None:
    print("=== 1. Trello Demo board ===")
    list_ids = await create_demo_board()

    print("\n=== 2. Tashkiliy tuzilma ===")
    org = await create_org_structure(list_ids)

    print("\n=== 3. Xodimlar ===")
    employees = await create_employees(org)

    print("\n=== 4. Mijozlar ===")
    clients = await create_clients()

    print("\n=== 5. Ishlab chiqarish vazifalari ===")
    tasks = await create_production_tasks(org, employees, clients)

    print("\n=== 6. Moliyaviy takliflar ===")
    financial = await create_financial_demo(org, employees)

    print("\n=== 7. Sotuv CRM ===")
    leads = await create_sales_demo(list_ids, employees)

    print("\n=== TAYYOR — jonli namoyish uchun cheat-sheet ===")
    print(f"ADMIN sifatida bog'lanish uchun /start bosib aynan shu ismni kiriting: {ADMIN_NAMES}")
    print(f"Stop holatidagi task (Davom ettirish tugmasi uchun): #{tasks['stop']}")
    print(f"8.3-band bilan boshqa brigadaga o'tkazilgan task: #{tasks['reassigned']}")
    print(f"PENDING_SETUP (muddat/xodim kiritish namoyishi) task: #{tasks['pending_setup']}")
    print(f"Yangi ACTIVE (Boshlash/Yakunlash namoyishi) tasklar: {tasks['fresh']}")
    print(f"MISC vazifalar (9-band): {tasks['misc']}")
    print(f"Moliyaviy takliflar (/moliyaviy, /avanskechirim): {financial}")
    print(f"Sotuv lidlar (/lidlarim): {leads}")


if __name__ == "__main__":
    asyncio.run(main())
