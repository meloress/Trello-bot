"""add starts_stopped to departments

Revision ID: 2ec88464a4f8
Revises: a1c9f3e7d502
Create Date: 2026-07-23 19:11:41.642577

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2ec88464a4f8'
down_revision = 'a1c9f3e7d502'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'departments' bo'sh emas — server_default majburiy (CLAUDE.md gotcha).
    # Eslatma: autogenerate 'leads.brand'/'leads.stage' uchun ham
    # alter_column taklif qildi (Enum(native_enum=False) vs VARCHAR(20) —
    # ikkalasi ham DB darajasida bir xil ustun, faqat autogenerate'ning
    # eski qatorlar bilan taqqoslash farqi) — bu migratsiya doirasidan
    # tashqari, ataylab olib tashlandi.
    op.add_column(
        'departments',
        sa.Column('starts_stopped', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('departments', 'starts_stopped')
