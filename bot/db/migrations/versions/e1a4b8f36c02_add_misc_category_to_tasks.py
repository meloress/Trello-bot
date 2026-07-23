"""add misc_category to tasks

Revision ID: e1a4b8f36c02
Revises: 83d73ef87edc
Create Date: 2026-07-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1a4b8f36c02'
down_revision = '83d73ef87edc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable — server_default shart emas (ORDER qatorlarida har doim NULL,
    # eski MISC qatorlarida ham kategoriya bo'lmasligi mumkin).
    op.add_column(
        'tasks',
        sa.Column('misc_category', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tasks', 'misc_category')
