"""add speed tier schedule and financial_suggestions speed tier columns

Revision ID: a3f7c9d02b41
Revises: 7b3d4bf8afe4
Create Date: 2026-07-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f7c9d02b41'
down_revision = '7b3d4bf8afe4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'app_settings' bo'sh emas (singleton) — server_default majburiy
    # (CLAUDE.md gotcha), 7b3d4bf8afe4'dagi bilan bir xil naqsh.
    op.add_column(
        'app_settings',
        sa.Column('speed_tier_schedule', sa.JSON(), nullable=False, server_default='[]'),
    )
    # 'financial_suggestions'ning boshqa 'kind'-ga xos ustunlari kabi
    # nullable, server_default kerak emas.
    op.add_column('financial_suggestions', sa.Column('speed_tier', sa.String(length=50), nullable=True))
    op.add_column('financial_suggestions', sa.Column('suggested_pay_amount', sa.Float(), nullable=True))
    # 'kind' ustuni native_enum=False (VARCHAR), uzunligi eng uzun mavjud
    # qiymatga qarab avtomatik belgilangan edi (VARCHAR(14) = "wage_deduction").
    # Yangi "speed_tier_bonus" (16 belgi) sig'may qoladi — 576f19bf5629'dagi
    # bilan bir xil naqsh (yangi uzunroq enum qiymati -> alter_column).
    op.alter_column(
        'financial_suggestions', 'kind',
        existing_type=sa.VARCHAR(length=14),
        type_=sa.Enum(
            'wage_deduction', 'advance_waiver', 'speed_tier_bonus',
            name='financial_suggestion_kind', native_enum=False,
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'financial_suggestions', 'kind',
        existing_type=sa.Enum(
            'wage_deduction', 'advance_waiver', 'speed_tier_bonus',
            name='financial_suggestion_kind', native_enum=False,
        ),
        type_=sa.VARCHAR(length=14),
        existing_nullable=False,
    )
    op.drop_column('financial_suggestions', 'suggested_pay_amount')
    op.drop_column('financial_suggestions', 'speed_tier')
    op.drop_column('app_settings', 'speed_tier_schedule')
