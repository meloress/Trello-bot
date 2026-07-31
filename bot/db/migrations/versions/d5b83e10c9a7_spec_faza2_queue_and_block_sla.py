"""SPEC.md Faza 2: navbat qoidasi (§5.2) va blok SLA (§5.3)

Revision ID: d5b83e10c9a7
Revises: c7f2a91b0d48
Create Date: 2026-07-31

Hammasi NULL/false standart bilan — sozlanmaguncha Faza 1 dagi oddiy
`default_sla_hours` xatti-harakati o'zgarishsiz qoladi.
"""

import sqlalchemy as sa
from alembic import op

revision = "d5b83e10c9a7"
down_revision = "c7f2a91b0d48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("daily_quota_orders", sa.Integer(), nullable=True))
    op.add_column("departments", sa.Column("sla_urgent_hours", sa.Integer(), nullable=True))
    op.add_column("departments", sa.Column("sla_over_quota_hours", sa.Integer(), nullable=True))
    op.add_column("departments", sa.Column("sla_block_id", sa.String(length=50), nullable=True))
    op.add_column(
        "tasks", sa.Column("is_urgent", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("tasks", "is_urgent")
    op.drop_column("departments", "sla_block_id")
    op.drop_column("departments", "sla_over_quota_hours")
    op.drop_column("departments", "sla_urgent_hours")
    op.drop_column("departments", "daily_quota_orders")
