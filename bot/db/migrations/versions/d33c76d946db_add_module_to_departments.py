"""add module to departments

Revision ID: d33c76d946db
Revises: 2ec88464a4f8
Create Date: 2026-07-23 19:30:59.448485

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd33c76d946db'
down_revision = '2ec88464a4f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'departments' bo'sh emas — server_default majburiy (CLAUDE.md gotcha).
    # Eslatma: autogenerate 'leads.brand'/'leads.stage' uchun ham
    # alter_column taklif qiladi (Enum(native_enum=False) vs VARCHAR(20) —
    # ikkalasi ham DB darajasida bir xil ustun, faqat autogenerate'ning
    # eski qatorlar bilan taqqoslash farqi) — bu migratsiya doirasidan
    # tashqari, ataylab olib tashlandi (avvalgi 2ec88464a4f8 migratsiyasida
    # ham xuddi shu holat bo'lgan).
    op.add_column(
        'departments',
        sa.Column('module', sa.String(length=20), nullable=False, server_default='mebel'),
    )


def downgrade() -> None:
    op.drop_column('departments', 'module')
