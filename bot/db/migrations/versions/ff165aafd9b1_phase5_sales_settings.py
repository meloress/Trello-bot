"""phase5 sales settings: lead_follow_up_threshold_days, sales_board_lists

Revision ID: ff165aafd9b1
Revises: b3f7a1c9d204
Create Date: 2026-07-17 16:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ff165aafd9b1'
down_revision = 'b3f7a1c9d204'
branch_labels = None
depends_on = None

_DEFAULT_BOARD_LISTS = json.dumps({
    "ezza": {"new_lead": None, "contacted": None, "offer_sent": None, "agreed": None, "closed": None},
    "melores": {"new_lead": None, "contacted": None, "offer_sent": None, "agreed": None, "closed": None},
})


def upgrade() -> None:
    # 13.3-band: "uzoq vaqt aloqaga chiqilmagan" mijoz chegarasi (kun),
    # foydalanuvchi bilan tasdiqlangan standart: 7.
    op.add_column(
        'app_settings',
        sa.Column('lead_follow_up_threshold_days', sa.Integer(), nullable=False, server_default='7'),
    )
    # 6.1-band: har (brand, bosqich) juftligi uchun Trello list ID, bot UI
    # orqali emas, to'g'ridan-to'g'ri bazada sozlanadi (departments.trello_list_id
    # bilan bir xil naqsh).
    op.add_column(
        'app_settings',
        sa.Column('sales_board_lists', sa.JSON(), nullable=False, server_default=_DEFAULT_BOARD_LISTS),
    )


def downgrade() -> None:
    op.drop_column('app_settings', 'sales_board_lists')
    op.drop_column('app_settings', 'lead_follow_up_threshold_days')
