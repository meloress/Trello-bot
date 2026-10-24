"""app_settings.nazorat_trello_cursor — Trello hodisalar jurnalida qayerda qolindi

Revision ID: b7e2c4d91a05
Revises: a4d1e6c20f93
Create Date: 2026-10-24

Nazorat Trello ball tizimi (`jobs/nazorat_trello_watch_job.py`) kartadan
odam olinganini ham ko'rishi shart — ko'rmasa ball umuman yozilmaydi. Shu
sabab kursor xotirada emas, bazada: deploy/qayta ishga tushishdan keyin job
qolgan joyidan davom etadi. NULL = hali ishga tushmagan (birinchi yurish
eski hodisalarni o'tkazib, kursorni hozirgi vaqtga qo'yadi).
"""

import sqlalchemy as sa
from alembic import op

revision = "b7e2c4d91a05"
down_revision = "a4d1e6c20f93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("nazorat_trello_cursor", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("app_settings", "nazorat_trello_cursor")
