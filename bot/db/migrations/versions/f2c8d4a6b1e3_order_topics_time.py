"""app_settings.order_topics_time — zakaz topiclariga ertalabki rasm vaqti

Revision ID: f2c8d4a6b1e3
Revises: e5b3a7c1d9f2
Create Date: 2026-11-23

Ilgari kodda qotib qolgan (08:00, 2026-11-23 dan 09:00) — endi Mini App
Sozlamalaridan o'zgartiriladi (foydalanuvchi, 2026-11-23).
"""

import sqlalchemy as sa
from alembic import op

revision = "f2c8d4a6b1e3"
down_revision = "e5b3a7c1d9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("order_topics_time", sa.String(5), nullable=False, server_default="09:00"),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "order_topics_time")
