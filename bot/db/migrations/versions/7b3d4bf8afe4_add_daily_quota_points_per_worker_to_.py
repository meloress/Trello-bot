"""add daily quota points per worker to app settings

Revision ID: 7b3d4bf8afe4
Revises: c8a2e6f31b90
Create Date: 2026-07-23 20:59:07.529786

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b3d4bf8afe4'
down_revision = 'c8a2e6f31b90'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'app_settings' bo'sh emas (singleton) — server_default majburiy
    # (CLAUDE.md gotcha). Autogenerate 'leads.brand'/'leads.stage' uchun ham
    # alter_column taklif qildi (Enum(native_enum=False) vs VARCHAR(20) —
    # 2ec88464a4f8'dagi bilan bir xil, faqat autogenerate-o'lchash farqi) —
    # bu migratsiya doirasidan tashqari, ataylab olib tashlandi.
    op.add_column(
        'app_settings',
        sa.Column('daily_quota_points_per_worker', sa.Integer(), nullable=False, server_default='5'),
    )


def downgrade() -> None:
    op.drop_column('app_settings', 'daily_quota_points_per_worker')
