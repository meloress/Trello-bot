"""add factory_name to departments

Revision ID: 3137620903a2
Revises: d33c76d946db
Create Date: 2026-07-23 19:45:45.582106

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3137620903a2'
down_revision = 'd33c76d946db'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, server_default shart emas (starts_stopped/module'dan farqli —
    # bu ustun hali belgilanmagan bo'limlar uchun NULL qoladi, CLAUDE.md
    # gotcha faqat NOT NULL ustunlarga tegishli).
    # Eslatma: autogenerate 'leads.brand'/'leads.stage' uchun ham
    # alter_column taklif qiladi (Enum(native_enum=False) vs VARCHAR(20) —
    # ikkalasi ham DB darajasida bir xil ustun) — bu migratsiya doirasidan
    # tashqari, ataylab olib tashlandi (avvalgi ikki migratsiyada ham xuddi
    # shu holat bo'lgan).
    op.add_column('departments', sa.Column('factory_name', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('departments', 'factory_name')
