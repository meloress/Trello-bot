"""order_topics — Nazorat Trello zakaz kartasi -> Telegram guruh topici

Revision ID: d9e4f2a7b1c3
Revises: c3f8a1d2e4b6
Create Date: 2026-11-05

Bot har bir yangi zakaz uchun guruhda topic ochadi (polniy uy uchun bitta) va
shablonni o'sha topicga yuboradi (`jobs/order_topics_job.py`). Qaysi kartaga
qaysi topic ochilgani va oxirgi yuborilgan holat shu jadvalda.
"""

import sqlalchemy as sa
from alembic import op

revision = "d9e4f2a7b1c3"
down_revision = "c3f8a1d2e4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.String(length=40), nullable=False),
        sa.Column("order_number", sa.String(length=10), nullable=True),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column("house_key", sa.String(length=200), nullable=True),
        sa.Column("topic_name", sa.String(length=128), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("card_id", name="uq_order_topics_card_id"),
    )


def downgrade() -> None:
    op.drop_table("order_topics")
