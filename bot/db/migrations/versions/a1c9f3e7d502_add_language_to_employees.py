"""Add language to employees (Mini App profile)

Revision ID: a1c9f3e7d502
Revises: 11e2c2cee985
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c9f3e7d502'
down_revision = '11e2c2cee985'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'employees',
        sa.Column('language', sa.String(length=2), server_default='uz', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('employees', 'language')
