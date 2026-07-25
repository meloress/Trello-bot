"""add trello ingest tracking columns to tasks

Revision ID: 77a6fe7328cd
Revises: 3c977b3a0d86
Create Date: 2026-07-26 00:00:00.000001

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '77a6fe7328cd'
down_revision = '3c977b3a0d86'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('trello_last_seen_list_id', sa.String(length=50), nullable=True))
    op.add_column('tasks', sa.Column('trello_last_seen_member_ids', sa.JSON(), nullable=True))
    op.add_column('tasks', sa.Column('trello_last_polled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'tasks', sa.Column('advanced_without_finish_claim_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('tasks', 'advanced_without_finish_claim_at')
    op.drop_column('tasks', 'trello_last_polled_at')
    op.drop_column('tasks', 'trello_last_seen_member_ids')
    op.drop_column('tasks', 'trello_last_seen_list_id')
