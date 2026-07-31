"""SPEC.md Faza 3: sex guruhi (§8), rahbar zanjiri (§7/§8), jarima maqsadi (§7)

Revision ID: e9c04a7f3b62
Revises: d5b83e10c9a7
Create Date: 2026-07-31

`penalize_all_assignees` standart `true` — bugungi xatti-harakat (hamma
javobgarga ball). Qolgan ikkitasi NULL — sozlanmaguncha hech narsa
o'zgarmaydi.
"""

import sqlalchemy as sa
from alembic import op

revision = "e9c04a7f3b62"
down_revision = "d5b83e10c9a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("telegram_chat_id", sa.String(length=50), nullable=True))
    op.add_column("employees", sa.Column("manager_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_employees_manager_id", "employees", "employees", ["manager_id"], ["id"]
    )
    op.add_column(
        "app_settings",
        sa.Column("penalize_all_assignees", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "penalize_all_assignees")
    op.drop_constraint("fk_employees_manager_id", "employees", type_="foreignkey")
    op.drop_column("employees", "manager_id")
    op.drop_column("departments", "telegram_chat_id")
