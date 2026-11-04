"""kpi_logs.score INTEGER -> NUMERIC(8,2) — Nazorat Trello jarimasi soatbay

Revision ID: c3f8a1d2e4b6
Revises: b7e2c4d91a05
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "c3f8a1d2e4b6"
down_revision = "b7e2c4d91a05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "kpi_logs", "score",
        type_=sa.Numeric(8, 2), existing_type=sa.Integer(), existing_nullable=False,
        postgresql_using="score::numeric(8,2)",
    )


def downgrade() -> None:
    op.alter_column(
        "kpi_logs", "score",
        type_=sa.Integer(), existing_type=sa.Numeric(8, 2), existing_nullable=False,
        postgresql_using="round(score)::integer",
    )
