"""phase5: task_sellers table + departments.stop_target_list_id

Revision ID: c8a2e6f31b90
Revises: b7c1e4f9a83d
Create Date: 2026-07-23 21:00:00.000000

Fasad sex TZ Phase 5 (Stop mechanism extensions), ikkalasi birga kiritiladi
(mustaqil, lekin bitta kichik migratsiya):
- `task_sellers` — buyurtmaga biriktirilgan sotuvchi(lar), Stop
  bildirishnomasi qo'shimcha qabul qiluvchilar sifatida (`task_assignments`
  bilan bir xil shakl).
- `departments.stop_target_list_id` — bo'lim darajasida ixtiyoriy: Stop
  bosilganda karta shu Trello ro'yxatiga ko'chirilsinmi (NULL = yo'q,
  mavjud mebel liniyasi uchun o'zgarishsiz).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8a2e6f31b90'
down_revision = 'b7c1e4f9a83d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, server_default shart emas (factory_name bilan bir xil
    # sabab — CLAUDE.md gotcha faqat NOT NULL ustunlarga tegishli).
    op.add_column('departments', sa.Column('stop_target_list_id', sa.String(length=50), nullable=True))

    op.create_table(
        'task_sellers',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='fk_task_sellers_task_id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name='fk_task_sellers_employee_id'),
        sa.UniqueConstraint('task_id', 'employee_id', name='uq_task_seller'),
    )


def downgrade() -> None:
    op.drop_table('task_sellers')
    op.drop_column('departments', 'stop_target_list_id')
