"""departments.is_hidden — bo'limni Mini App ro'yxatlaridan yashirish

Revision ID: a4d1e6c20f93
Revises: e9c04a7f3b62
Create Date: 2026-09-25

Foydalanuvchi talabi: Nazorat Trello'da xodim/bo'lim ro'yxatlarida faqat
11 ta bo'lim ko'rinsin, qolganlari o'chirilmasin (buyurtma zanjiri
buzilmasin). Standart `false` — mavjud bo'limlarning hammasi ko'rinib turadi.
"""

import sqlalchemy as sa
from alembic import op

revision = "a4d1e6c20f93"
down_revision = "e9c04a7f3b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "departments",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("departments", "is_hidden")
