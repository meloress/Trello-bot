"""SPEC.md Faza 1: SLA dvigateli (§5.1 bo'lim SLA, §6.1 STOP muzlatishi, §5.4 eslatmalar)

Revision ID: c7f2a91b0d48
Revises: b4e17c9a2d31
Create Date: 2026-07-31

Barcha ustunlar `server_default` bilan qo'shiladi (jadvallar bo'sh emas) va
standart qiymatlar bugungi xatti-harakatni saqlaydi:
- `departments.default_sla_hours` NULL = SLA yo'q (muddat qo'lda kiritiladi);
- `tasks.stopped_seconds_total` 0 = hali "Stop" hisoblanmagan;
- `app_settings.deadline_warning_hours` 4 / `overdue_repeat_hours` 12 —
  TZ §5.4 dagi standartlar.
"""

import sqlalchemy as sa
from alembic import op

revision = "c7f2a91b0d48"
down_revision = "b4e17c9a2d31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("default_sla_hours", sa.Integer(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("stopped_seconds_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tasks", sa.Column("last_overdue_reminder_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "app_settings",
        sa.Column("deadline_warning_hours", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "app_settings",
        sa.Column("overdue_repeat_hours", sa.Integer(), nullable=False, server_default="12"),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "overdue_repeat_hours")
    op.drop_column("app_settings", "deadline_warning_hours")
    op.drop_column("tasks", "last_overdue_reminder_at")
    op.drop_column("tasks", "stopped_seconds_total")
    op.drop_column("departments", "default_sla_hours")
