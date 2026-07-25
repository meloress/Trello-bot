"""add stopped_auto_resume_after_hours to departments

Revision ID: f3a7c1d9e4b6
Revises: e1a4b8f36c02
Create Date: 2026-07-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a7c1d9e4b6'
down_revision = 'e1a4b8f36c02'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, default NULL — most starts_stopped departments (e.g. "Zakaz
    # tushdi") wait for a manual real-world signal, not a timeout. Only a
    # department that explicitly opts in (e.g. Sklad) gets a value here.
    op.add_column(
        'departments',
        sa.Column('stopped_auto_resume_after_hours', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('departments', 'stopped_auto_resume_after_hours')
