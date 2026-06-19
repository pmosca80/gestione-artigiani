"""add prima nota

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'prima_nota',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utente_id', sa.Integer(), sa.ForeignKey('utenti.id'), nullable=False),
        sa.Column('data', sa.String(), nullable=False),
        sa.Column('descrizione', sa.String(), nullable=False),
        sa.Column('importo', sa.Float(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False, server_default='uscita'),
        sa.Column('categoria', sa.String(), nullable=True),
        sa.Column('data_creazione', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_prima_nota_utente_data', 'prima_nota', ['utente_id', 'data'])


def downgrade() -> None:
    op.drop_index('ix_prima_nota_utente_data', 'prima_nota')
    op.drop_table('prima_nota')
