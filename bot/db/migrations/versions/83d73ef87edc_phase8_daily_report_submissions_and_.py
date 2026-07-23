"""phase8 daily report submissions and required flag

Revision ID: 83d73ef87edc
Revises: a3f7c9d02b41
Create Date: 2026-07-24 01:05:51.253099

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '83d73ef87edc'
down_revision = 'a3f7c9d02b41'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'daily_report_submissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.String(length=200), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['employee_id'], ['employees.id'], name='fk_daily_report_submissions_employee_id'
        ),
        sa.UniqueConstraint(
            'employee_id', 'report_date', name='uq_daily_report_submissions_employee_date'
        ),
    )

    # 'employees' bo'sh emas — server_default majburiy (CLAUDE.md gotcha).
    op.add_column(
        'employees',
        sa.Column('daily_report_required', sa.Boolean(), nullable=False, server_default='false'),
    )
    # 'app_settings' bo'sh emas (singleton) — bir xil sabab, 'report_time'dagi
    # bilan bir xil naqsh.
    op.add_column(
        'app_settings',
        sa.Column('daily_report_time', sa.String(length=5), nullable=False, server_default='09:00'),
    )


def downgrade() -> None:
    op.drop_column('app_settings', 'daily_report_time')
    op.drop_column('employees', 'daily_report_required')
    op.drop_table('daily_report_submissions')
