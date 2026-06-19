"""add registro fatture

Revision ID: c3a1f9e2d8b7
Revises: bf104c2ea4db
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a1f9e2d8b7'
down_revision: Union[str, Sequence[str], None] = 'bf104c2ea4db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lavori', sa.Column('stato_fattura', sa.String(), nullable=True))
    op.add_column('impostazioni_azienda', sa.Column('ultimo_numero_fattura', sa.Integer(), nullable=True, server_default='0'))
    op.create_table(
        'fatture_emesse',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('utente_id', sa.Integer(), sa.ForeignKey('utenti.id'), nullable=False),
        sa.Column('lavoro_id', sa.Integer(), sa.ForeignKey('lavori.id'), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('anno', sa.Integer(), nullable=False),
        sa.Column('data_emissione', sa.String(), nullable=False),
        sa.Column('importo_imponibile', sa.Float(), nullable=True),
        sa.Column('importo_iva', sa.Float(), nullable=True),
        sa.Column('importo_totale', sa.Float(), nullable=True),
        sa.Column('nome_file', sa.String(), nullable=True),
        sa.Column('regime', sa.String(), nullable=True),
        sa.Column('stato', sa.String(), nullable=False, server_default='emessa'),
        sa.Column('data_creazione', sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('fatture_emesse')
    op.drop_column('impostazioni_azienda', 'ultimo_numero_fattura')
    op.drop_column('lavori', 'stato_fattura')
