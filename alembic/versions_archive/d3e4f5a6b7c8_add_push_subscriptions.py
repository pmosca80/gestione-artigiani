"""add push_subscriptions

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utente_id', sa.Integer(), sa.ForeignKey('utenti.id'), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('subscription_json', sa.Text(), nullable=False),
        sa.Column('creata_il', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_push_sub_utente', 'push_subscriptions', ['utente_id'])


def downgrade() -> None:
    op.drop_index('ix_push_sub_utente', 'push_subscriptions')
    op.drop_table('push_subscriptions')
