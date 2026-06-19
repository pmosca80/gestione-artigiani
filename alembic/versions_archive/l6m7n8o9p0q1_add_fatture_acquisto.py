"""add fatture_acquisto table

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'l6m7n8o9p0q1'
down_revision = 'k5l6m7n8o9p0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fatture_acquisto',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utente_id', sa.Integer(), nullable=False),
        sa.Column('fornitore_id', sa.Integer(), nullable=True),
        sa.Column('lavoro_id', sa.Integer(), nullable=True),
        sa.Column('numero_fattura', sa.String(), nullable=True),
        sa.Column('data_fattura', sa.Date(), nullable=False),
        sa.Column('anno', sa.Integer(), nullable=False),
        sa.Column('data_scadenza', sa.Date(), nullable=True),
        sa.Column('descrizione', sa.String(), nullable=False),
        sa.Column('categoria', sa.String(), nullable=True),
        sa.Column('importo_imponibile', sa.Float(), nullable=True, server_default='0'),
        sa.Column('aliquota_iva', sa.Float(), nullable=True, server_default='22'),
        sa.Column('importo_iva', sa.Float(), nullable=True, server_default='0'),
        sa.Column('importo_totale', sa.Float(), nullable=True, server_default='0'),
        sa.Column('stato_pagamento', sa.String(), nullable=False, server_default='da_pagare'),
        sa.Column('data_pagamento', sa.Date(), nullable=True),
        sa.Column('metodo_pagamento', sa.String(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('data_creazione', sa.DateTime(), nullable=False),
        sa.Column('data_aggiornamento', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['fornitore_id'], ['fornitori.id']),
        sa.ForeignKeyConstraint(['lavoro_id'], ['lavori.id']),
        sa.ForeignKeyConstraint(['utente_id'], ['utenti.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fatture_acquisto_utente_id', 'fatture_acquisto', ['utente_id'])
    op.create_index('ix_fatture_acquisto_utente_anno', 'fatture_acquisto', ['utente_id', 'anno'])


def downgrade():
    op.drop_index('ix_fatture_acquisto_utente_anno', table_name='fatture_acquisto')
    op.drop_index('ix_fatture_acquisto_utente_id', table_name='fatture_acquisto')
    op.drop_table('fatture_acquisto')
