"""departments.trello_label + silent_penalty — Trello'ga kirmaydigan bo'lim (raspil)

Revision ID: e5b3a7c1d9f2
Revises: d9e4f2a7b1c3
Create Date: 2026-11-12

Raspilchilar Trello'ga a'zo qilinmaydi (foydalanuvchi, 2026-11-12): kartaga
shu nomli label qo'yilganda zakaz bo'limning hamma ishchisiga beriladi, label
olinganda tugaydi (`jobs/nazorat_trello_watch_job.py`). `silent_penalty` —
ball yoziladi, lekin xodimning o'ziga aytilmaydi (faqat rahbar/nazoratchi).
"""

import sqlalchemy as sa
from alembic import op

revision = "e5b3a7c1d9f2"
down_revision = "d9e4f2a7b1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("trello_label", sa.String(50), nullable=True))
    op.add_column(
        "departments",
        sa.Column("silent_penalty", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("departments", "silent_penalty")
    op.drop_column("departments", "trello_label")
