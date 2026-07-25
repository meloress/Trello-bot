"""add task_claims table

Revision ID: 3c977b3a0d86
Revises: f3a7c1d9e4b6
Create Date: 2026-07-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3c977b3a0d86'
down_revision = 'f3a7c1d9e4b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'task_claims',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column(
            'action_type',
            sa.Enum('pause', 'finish', name='claim_action_type', native_enum=False),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('pending', 'approved', 'rejected', name='claim_status', native_enum=False),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('reviewed_by_employee_id', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_note', sa.Text(), nullable=True),
        sa.Column('last_reminder_stage', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='fk_task_claims_task_id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name='fk_task_claims_employee_id'),
        sa.ForeignKeyConstraint(
            ['reviewed_by_employee_id'], ['employees.id'], name='fk_task_claims_reviewed_by_employee_id'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Bir vaqtda faqat bitta PENDING claim bo'lishi mumkin (bitta task uchun) —
    # ilova darajasidagi tekshiruv (get_pending_for_task) ustiga qo'yilgan
    # DB darajasidagi kafolat (race condition'ga qarshi).
    op.create_index(
        'uq_task_claims_one_pending', 'task_claims', ['task_id'], unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index('uq_task_claims_one_pending', table_name='task_claims')
    op.drop_table('task_claims')
