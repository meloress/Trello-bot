"""phase5 leads and call_logs tables

Revision ID: 11e2c2cee985
Revises: ff165aafd9b1
Create Date: 2026-07-17 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '11e2c2cee985'
down_revision = 'ff165aafd9b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'leads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('brand', sa.String(length=20), nullable=False),
        sa.Column('stage', sa.String(length=20), nullable=False),
        sa.Column('assigned_seller_id', sa.Integer(), nullable=False),
        sa.Column('trello_card_id', sa.String(length=50), nullable=True),
        sa.Column('last_contacted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name='fk_leads_client_id'),
        sa.ForeignKeyConstraint(['assigned_seller_id'], ['employees.id'], name='fk_leads_assigned_seller_id'),
    )
    op.create_table(
        'call_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('recorded_by_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('audio_file_id', sa.String(length=200), nullable=True),
        sa.Column('called_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], name='fk_call_logs_lead_id'),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['employees.id'], name='fk_call_logs_recorded_by_id'),
    )


def downgrade() -> None:
    op.drop_table('call_logs')
    op.drop_table('leads')
