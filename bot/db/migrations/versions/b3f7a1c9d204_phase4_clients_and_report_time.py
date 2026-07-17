"""phase4 clients table, tasks.client_id, app_settings.report_time

Revision ID: b3f7a1c9d204
Revises: f98817708ac9
Create Date: 2026-07-17 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f7a1c9d204'
down_revision = 'f98817708ac9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 12-band: mijozlarga avtomatik xabarnoma. Minimal, CRM-spetsifik bo'lmagan
    # maydonlar — 5-bosqich (Sotuv CRM) shu jadvalni kengaytirishi mumkin.
    op.create_table(
        'clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=True),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone_number', name='uq_clients_phone_number'),
        sa.UniqueConstraint('telegram_id', name='uq_clients_telegram_id'),
    )

    op.add_column('tasks', sa.Column('client_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_tasks_client_id', 'tasks', 'clients', ['client_id'], ['id']
    )

    # 10.2-band: kunlik/haftalik/oylik hisobot vaqti (16-band: sozlanuvchan,
    # kodga tikilmagan). server_default kerak — app_settings'da bitta seed
    # qator bor (CLAUDE.md gotcha).
    op.add_column(
        'app_settings', sa.Column('report_time', sa.String(length=5), nullable=False, server_default='20:00')
    )


def downgrade() -> None:
    op.drop_column('app_settings', 'report_time')

    op.drop_constraint('fk_tasks_client_id', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'client_id')

    op.drop_table('clients')
