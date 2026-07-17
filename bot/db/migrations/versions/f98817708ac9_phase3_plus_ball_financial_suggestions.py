"""phase3 plus ball settings, financial_suggestions table, penalty_rules grace period shift

Revision ID: f98817708ac9
Revises: 470b837c8dae
Create Date: 2026-07-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f98817708ac9'
down_revision = '470b837c8dae'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 8.4-band: plus ball + 8.6-band: moliyaviy bayroqlash uchun yangi
    # sozlanuvchan skalyarlar (16-band: kodga tikilmasin). server_default
    # qo'lda qo'shildi (CLAUDE.md gotcha: app_settings'da allaqachon 1 ta
    # seed qator bor).
    op.add_column('app_settings', sa.Column('plus_ball_per_day', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('app_settings', sa.Column('plus_ball_max_days', sa.Integer(), nullable=False, server_default='2'))
    op.add_column(
        'app_settings',
        sa.Column('financial_flag_threshold_days', sa.Integer(), nullable=False, server_default='5'),
    )
    op.add_column(
        'app_settings',
        sa.Column('advance_threshold_percent', sa.Integer(), nullable=False, server_default='80'),
    )
    op.add_column(
        'app_settings',
        sa.Column('advance_waiver_percent', sa.Integer(), nullable=False, server_default='20'),
    )

    # 8.1/8.2-band: 24 soatlik "grace period" endi kodda hisoblanadi
    # (penalty_service.calculate_and_apply_task_penalty: hours_late<24 ->
    # jarima yo'q) — shu sabab mavjud bracket'lar +24 soatga siljitiladi
    # (score'lar o'zgarmaydi): [0,24)->[24,48), [24,48)->[48,72), va h.k.
    # Faqat department_id IS NULL (global) qatorlarga tegadi — bu bosqichda
    # boshqa qator yo'q.
    op.execute(
        "UPDATE penalty_rules SET "
        "min_hours_late = min_hours_late + 24, "
        "max_hours_late = CASE WHEN max_hours_late IS NULL THEN NULL ELSE max_hours_late + 24 END "
        "WHERE department_id IS NULL"
    )

    op.create_table(
        'financial_suggestions',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('wage_deduction', 'advance_waiver', name='financial_suggestion_kind', native_enum=False),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'pending_manager_review', 'approved', 'rejected',
                name='financial_suggestion_status', native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('applicable', sa.Boolean(), nullable=False),
        sa.Column('stage_duration_days', sa.Integer(), nullable=True),
        sa.Column('amount_withheld_by_customer', sa.Float(), nullable=True),
        sa.Column('suggested_deduction_amount', sa.Float(), nullable=True),
        sa.Column('advance_percent_paid', sa.Integer(), nullable=True),
        sa.Column('order_total_value', sa.Float(), nullable=True),
        sa.Column('waived_amount', sa.Float(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='fk_financial_suggestions_task_id'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('financial_suggestions')

    op.execute(
        "UPDATE penalty_rules SET "
        "min_hours_late = min_hours_late - 24, "
        "max_hours_late = CASE WHEN max_hours_late IS NULL THEN NULL ELSE max_hours_late - 24 END "
        "WHERE department_id IS NULL"
    )

    op.drop_column('app_settings', 'advance_waiver_percent')
    op.drop_column('app_settings', 'advance_threshold_percent')
    op.drop_column('app_settings', 'financial_flag_threshold_days')
    op.drop_column('app_settings', 'plus_ball_max_days')
    op.drop_column('app_settings', 'plus_ball_per_day')
