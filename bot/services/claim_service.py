"""Ishchi Mini App'da Pauza/Yakunlash bosganda yaratiladigan "so'rov"
(claim) — mebel moduli uchun. Haqiqiy TaskStatus/StopLog o'zgarishi FAQAT
bo'lim rahbari (SUPERVISOR/ADMIN) tasdiqlagandan keyin sodir bo'ladi, va
`timer_service.finish_task`/`stop_task`ga ishchi TUGMANI BOSGAN aniq vaqt
(`claim.claimed_at`) uzatiladi — tasdiqlash necha soat/kun kechiksa ham
ball hisob-kitobiga ta'sir qilmasligi uchun. Rad etilsa — hech qanday
task/StopLog mutatsiyasi bo'lmaydi, vazifa xuddi so'rov bo'lmagandek davom
etadi.
"""

import logging
from datetime import datetime, timezone

from core.database import async_session
from db.models.task_claim import TaskClaim
from db.repositories import EmployeeRepository, TaskClaimRepository, TaskRepository
from services import notification_service, penalty_service, timer_service
from utils.enums import ClaimActionType, ClaimStatus, Role, TaskStatus

logger = logging.getLogger(__name__)


async def _notify_supervisors_safely(fn, bot, *args) -> None:
    """Bildirishnoma — ikkilamchi ta'sir: xatosi tasdiqlashni bekor qilmasligi
    kerak. `bot=None` (skript/smoke chaqiruvlari) — jim o'tkaziladi."""
    if bot is None:
        return
    try:
        await fn(bot, *args)
    except Exception:
        logger.exception("approve_claim: nazoratchi bildirishnomasi yuborilmadi (%s)", fn.__name__)


class ClaimNotFoundError(Exception):
    """Berilgan claim_id topilmadi."""


class ClaimAlreadyPendingError(Exception):
    """Shu task_id uchun allaqachon ko'rib chiqilmagan (PENDING) so'rov bor."""


class InvalidClaimStateError(Exception):
    """So'ralgan amal claim'ning joriy holatiga mos kelmaydi (allaqachon ko'rib chiqilgan)."""


class NotAuthorizedToReviewError(Exception):
    """Berilgan rahbar ushbu so'rovni tasdiqlash/rad etish doirasida emas."""


async def submit_claim(
    task_id: int,
    employee_id: int,
    action_type: ClaimActionType,
    claimed_at: datetime,
    reason: str | None = None,
) -> TaskClaim:
    """Ishchi Mini App'da tugmani bosganda chaqiriladi. `claimed_at` —
    chaqiruvchi (`miniapp/api/worker.py`) tugma bosilgan ANIQ vaqtni
    uzatadi (odatda `datetime.now(timezone.utc)`, lekin bu funksiya buni
    o'zi belgilamaydi — chaqiruvchi javobgar)."""
    if action_type == ClaimActionType.PAUSE and not (reason and reason.strip()):
        raise ValueError("Pauza so'rovi uchun sabab (reason) bo'sh bo'lishi mumkin emas")

    async with async_session() as session:
        claim_repo = TaskClaimRepository(session)

        existing = await claim_repo.get_pending_for_task(task_id)
        if existing is not None:
            raise ClaimAlreadyPendingError(f"Task {task_id} uchun allaqachon ko'rib chiqilmagan so'rov bor")

        claim = await claim_repo.create(
            task_id=task_id,
            employee_id=employee_id,
            action_type=action_type,
            status=ClaimStatus.PENDING,
            claimed_at=claimed_at,
            reason=reason,
        )
        await session.commit()
        return claim


async def _reviewer_in_scope(session, reviewer_employee_id: int, task_department_id: int | None) -> bool:
    """`miniapp/api/admin.py`dagi `_department_scope_ok` bilan bir xil
    qoida: ADMIN va bo'limsiz SUPERVISOR cheklanmagan, boshqa SUPERVISOR
    faqat o'z bo'limi doirasida."""
    employee = await EmployeeRepository(session).get_by_id(reviewer_employee_id)
    if employee is None:
        return False
    if employee.role == Role.ADMIN or employee.department_id is None:
        return True
    return employee.department_id == task_department_id


async def list_pending_claims_for_supervisor(employee_id: int) -> list[TaskClaim]:
    """Rahbar/admin ko'rish ro'yxati — `miniapp/api/admin.py`'ning
    `GET /pending-claims` shu funksiyani chaqiradi. ADMIN yoki bo'limsiz
    SUPERVISOR — hammasi; boshqa SUPERVISOR — faqat o'z bo'limidagi
    vazifalarga tegishli so'rovlar. Har ikkala tarmoqda ham task allaqachon
    COMPLETED bo'lgan (yoki umuman topilmagan) claim'lar chetlab o'tiladi —
    bunday claim `approve_claim()`da hech qachon muvaffaqiyatli
    qo'llanolmaydi (task holati allaqachon o'zgargan), shu sabab uni
    ko'rib-chiqish navbatida ko'rsatishning ma'nosi yo'q."""
    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_id(employee_id)
        if employee is None:
            return []

        claim_repo = TaskClaimRepository(session)
        task_repo = TaskRepository(session)
        claims = await claim_repo.list_pending()

        unrestricted = employee.role == Role.ADMIN or employee.department_id is None

        scoped = []
        for claim in claims:
            task = await task_repo.get_by_id(claim.task_id)
            if task is None or task.status == TaskStatus.COMPLETED:
                continue
            if unrestricted or task.current_department_id == employee.department_id:
                scoped.append(claim)
        return scoped


async def approve_claim(claim_id: int, reviewer_employee_id: int, bot=None) -> TaskClaim:
    """Tasdiqlash: haqiqiy holat o'zgarishi ENDI sodir bo'ladi, lekin
    `finished_at`/`stopped_at` sifatida ishchi bosgan ORIGINAL vaqt
    (`claim.claimed_at`) ishlatiladi — rahbar TASDIQLAGAN vaqt emas. Avval
    haqiqiy mutatsiya (timer_service/penalty_service) bajariladi, FAQAT
    muvaffaqiyatli bo'lsa claim `APPROVED` deb belgilanadi (aks holda
    xatolik chaqiruvchiga otiladi, claim PENDING holicha qoladi) —
    `task_service.reassign_task_brigade()`dagi "o'qi -> tashqi chaqiruv ->
    qayta yoz" uch bosqichli naqsh bilan bir xil.

    "Yakunlash" so'rovi `penalty_service.finalize_task_and_apply_penalty()`
    orqali o'tadi (avval bu yerda `finish_task` + `calculate_and_apply_task_penalty`
    qo'lda ketma-ket chaqirilardi) — o'sha yagona funksiya yakunlash, ball
    hisoblash, BILDIRISHNOMA va xato holatlarini birga hal qiladi. Qo'lda
    chaqirishning ikkita haqiqiy oqibati bor edi: (1) ball yozilardi-yu ishchiga
    hech qanday xabar bormasdi, (2) kechikish `penalty_rules` qamrovidan
    tashqarida bo'lsa (`PenaltyRuleNotConfiguredError`) xato yuqoriga otilib,
    vazifa allaqachon COMPLETED bo'lgani holda claim abadiy PENDING bo'lib
    qolardi va rahbarga 500 qaytardi."""
    async with async_session() as session:
        claim_repo = TaskClaimRepository(session)
        claim = await claim_repo.get_by_id(claim_id)
        if claim is None:
            raise ClaimNotFoundError(f"Claim {claim_id} topilmadi")
        if claim.status != ClaimStatus.PENDING:
            raise InvalidClaimStateError(f"Claim {claim_id} allaqachon ko'rib chiqilgan (holat: {claim.status})")

        task = await TaskRepository(session).get_by_id(claim.task_id)
        task_department_id = task.current_department_id if task is not None else None
        if not await _reviewer_in_scope(session, reviewer_employee_id, task_department_id):
            raise NotAuthorizedToReviewError(f"Xodim {reviewer_employee_id} bu so'rovni tasdiqlash doirasida emas")

        action_type = claim.action_type
        task_id = claim.task_id
        employee_id = claim.employee_id
        claimed_at = claim.claimed_at
        reason = claim.reason

    try:
        if action_type == ClaimActionType.FINISH:
            # Yakunlash + ball + bildirishnoma + xato holatlari — hammasi shu
            # yagona funksiyada (o'zi InvalidTaskStateError/TaskNotFoundError/
            # PenaltyRuleNotConfiguredError'ni yutib, log qilib o'tkazadi).
            await penalty_service.finalize_task_and_apply_penalty(
                bot, task_id, finished_at=claimed_at, employee_id=employee_id
            )
        elif action_type == ClaimActionType.RESUME:
            # Davom ettirishda `claimed_at` ishlatilmaydi: `resume_task` faqat
            # STOPPED -> ACTIVE holatini qaytaradi va `stop_logs`ning ochiq
            # yozuvini yopadi, muddat/ball hisobi to'xtash vaqtiga bog'liq
            # emas — shu sabab tasdiqlash kechikishi bu yerda ta'sir qilmaydi.
            await timer_service.resume_task(task_id, employee_id)
            # Amal HAQIQATAN bajarilgandan keyin nazoratchiga xabar. Ilgari bu
            # yo'l hech qanday xabar yubormasdi: ish to'xtaganini/qayta
            # boshlanganini so'rov yuborgan odamdan boshqa hech kim bilmasdi.
            await _notify_supervisors_safely(
                notification_service.notify_stage_resumed, bot, task_id, employee_id
            )
        else:
            await timer_service.stop_task(task_id, employee_id, reason or "", stopped_at=claimed_at)
            await _notify_supervisors_safely(
                notification_service.notify_stage_paused, bot, task_id, employee_id, reason
            )
    except (timer_service.InvalidTaskStateError, timer_service.TaskNotFoundError) as exc:
        # Claim soatlab PENDING turgan bo'lishi mumkin (eskalatsiya +24 soatgacha),
        # shu orada task mustaqil ravishda holat almashtirgan bo'lishi mumkin
        # (masalan `trello_ingest_job.finalize_task_and_apply_penalty` karta
        # arxivlanganda, yoki `overdue_watch_job` ACTIVE->OVERDUE). Bunday holda
        # rahbarning tasdig'i baribir HISOBGA OLINADI (claim APPROVED bo'ladi) —
        # lekin mutatsiyani qayta ijro etib bo'lmaydi, shu sabab faqat log qilib
        # o'tkazib yuboriladi (rahbarga xato ko'rsatib, claim'ni abadiy PENDING
        # holatda qoldirish o'rniga).
        logger.warning(
            "approve_claim: task holati o'zgargan, mutatsiya qayta ijro etilmadi "
            "(claim_id=%s, task_id=%s, action_type=%s): %s",
            claim_id, task_id, action_type, exc,
        )

    async with async_session() as session:
        claim_repo = TaskClaimRepository(session)
        claim = await claim_repo.get_by_id(claim_id)
        await claim_repo.update(
            claim,
            status=ClaimStatus.APPROVED,
            reviewed_by_employee_id=reviewer_employee_id,
            reviewed_at=datetime.now(timezone.utc),
        )
        await session.commit()
        return claim


async def reject_claim(claim_id: int, reviewer_employee_id: int, note: str | None = None) -> TaskClaim:
    """Rad etish: hech qanday task/timer mutatsiyasi YO'Q — claim hali
    hech narsani o'zgartirmagan edi (haqiqiy holat o'zgarishi faqat
    `approve_claim()`da sodir bo'ladi), shuning uchun "bekor qilish" shunchaki
    claim statusini yozish bilan tugaydi, vazifa avvalgidek davom etadi."""
    async with async_session() as session:
        claim_repo = TaskClaimRepository(session)
        claim = await claim_repo.get_by_id(claim_id)
        if claim is None:
            raise ClaimNotFoundError(f"Claim {claim_id} topilmadi")
        if claim.status != ClaimStatus.PENDING:
            raise InvalidClaimStateError(f"Claim {claim_id} allaqachon ko'rib chiqilgan (holat: {claim.status})")

        task = await TaskRepository(session).get_by_id(claim.task_id)
        task_department_id = task.current_department_id if task is not None else None
        if not await _reviewer_in_scope(session, reviewer_employee_id, task_department_id):
            raise NotAuthorizedToReviewError(f"Xodim {reviewer_employee_id} bu so'rovni rad etish doirasida emas")

        await claim_repo.update(
            claim,
            status=ClaimStatus.REJECTED,
            reviewed_by_employee_id=reviewer_employee_id,
            reviewed_at=datetime.now(timezone.utc),
            rejection_note=note,
        )
        await session.commit()
        return claim
