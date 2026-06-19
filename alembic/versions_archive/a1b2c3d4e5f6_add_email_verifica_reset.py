"""add email verifica e reset password a utenti

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('utenti', sa.Column('email', sa.String(), nullable=True))
    op.add_column('utenti', sa.Column('email_verificato', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('utenti', sa.Column('token_verifica', sa.String(), nullable=True))
    op.add_column('utenti', sa.Column('token_reset', sa.String(), nullable=True))
    op.add_column('utenti', sa.Column('token_reset_scadenza', sa.String(), nullable=True))
    op.add_column('utenti', sa.Column('accetta_termini', sa.Boolean(), nullable=True, server_default='false'))


def downgrade() -> None:
    op.drop_column('utenti', 'accetta_termini')
    op.drop_column('utenti', 'token_reset_scadenza')
    op.drop_column('utenti', 'token_reset')
    op.drop_column('utenti', 'token_verifica')
    op.drop_column('utenti', 'email_verificato')
    op.drop_column('utenti', 'email')
