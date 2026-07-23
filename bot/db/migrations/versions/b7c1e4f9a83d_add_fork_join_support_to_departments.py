"""add fork/join support to departments

Revision ID: b7c1e4f9a83d
Revises: 3137620903a2
Create Date: 2026-07-23 20:30:00.000000

Fasad sex TZ (Phase 3): fork/join zanjiri. Ikkalasi birga kiritiladi —
`departments.requires_join` (konvergensiya bo'limi bayrog'i) va yangi
`department_fork_targets` jadvali (fork nuqtasi -> N parallel tarmoq).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c1e4f9a83d'
down_revision = '3137620903a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'departments' bo'sh emas — server_default majburiy (CLAUDE.md gotcha,
    # starts_stopped/module bilan bir xil).
    op.add_column(
        'departments',
        sa.Column('requires_join', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Ikkala FK ham 'departments'ga ishora qiladi — explicit nom majburiy
    # (CLAUDE.md gotcha: autogenerate None nomli FK chiqarib downgrade'ni buzadi).
    op.create_table(
        'department_fork_targets',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('target_department_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['department_id'], ['departments.id'], name='fk_department_fork_targets_department_id'
        ),
        sa.ForeignKeyConstraint(
            ['target_department_id'], ['departments.id'],
            name='fk_department_fork_targets_target_department_id',
        ),
        sa.UniqueConstraint('department_id', 'target_department_id', name='uq_department_fork_target'),
    )


def downgrade() -> None:
    op.drop_table('department_fork_targets')
    op.drop_column('departments', 'requires_join')
