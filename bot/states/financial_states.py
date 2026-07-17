from aiogram.fsm.state import State, StatesGroup


class WageDeductionAmountStates(StatesGroup):
    """8.6-band 1-qoida: admin avtomatik bayroqlangan taklifga mijoz ushlab
    qolgan summani qo'lda kiritadi (`/moliyaviy`)."""

    waiting_for_amount = State()


class AdvanceWaiverStates(StatesGroup):
    """8.6-band 2-qoida: admin qo'lda task_id + avans/buyurtma ma'lumotlarini
    kiritib taklif yaratadi (`/avanskechirim`) — avtomatik manba yo'q."""

    waiting_for_task_id = State()
    waiting_for_advance_percent = State()
    waiting_for_order_value = State()
    waiting_for_is_late = State()
