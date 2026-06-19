"""add piano e stripe a utenti

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('utenti', sa.Column('piano', sa.String(), nullable=True, server_default='free'))
    op.add_column('utenti', sa.Column('stripe_customer_id', sa.String(), nullable=True))
    op.add_column('utenti', sa.Column('stripe_subscription_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('utenti', 'stripe_subscription_id')
    op.drop_column('utenti', 'stripe_customer_id')
    op.drop_column('utenti', 'piano')
