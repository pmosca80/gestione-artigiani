"""add fatturapa fields

Revision ID: bf104c2ea4db
Revises: 8e0594ee3d95
Create Date: 2026-06-11 18:22:46.480261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf104c2ea4db'
down_revision: Union[str, Sequence[str], None] = '8e0594ee3d95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clienti', sa.Column('partita_iva', sa.String(), nullable=True))
    op.add_column('clienti', sa.Column('codice_fiscale', sa.String(), nullable=True))
    op.add_column('clienti', sa.Column('codice_destinatario', sa.String(), nullable=True))
    op.add_column('clienti', sa.Column('pec_destinatario', sa.String(), nullable=True))
    op.add_column('impostazioni_azienda', sa.Column('codice_fiscale', sa.String(), nullable=True))
    op.add_column('impostazioni_azienda', sa.Column('regime_fiscale', sa.String(), nullable=True))
    op.add_column('impostazioni_azienda', sa.Column('cap', sa.String(), nullable=True))
    op.add_column('impostazioni_azienda', sa.Column('citta', sa.String(), nullable=True))
    op.add_column('impostazioni_azienda', sa.Column('provincia', sa.String(), nullable=True))
    op.add_column('lavori', sa.Column('numero_fattura', sa.Integer(), nullable=True))
    op.add_column('lavori', sa.Column('data_fattura', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('lavori', 'data_fattura')
    op.drop_column('lavori', 'numero_fattura')
    op.drop_column('impostazioni_azienda', 'provincia')
    op.drop_column('impostazioni_azienda', 'citta')
    op.drop_column('impostazioni_azienda', 'cap')
    op.drop_column('impostazioni_azienda', 'regime_fiscale')
    op.drop_column('impostazioni_azienda', 'codice_fiscale')
    op.drop_column('clienti', 'pec_destinatario')
    op.drop_column('clienti', 'codice_destinatario')
    op.drop_column('clienti', 'codice_fiscale')
    op.drop_column('clienti', 'partita_iva')
