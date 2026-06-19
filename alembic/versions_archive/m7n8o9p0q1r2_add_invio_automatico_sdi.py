"""add invio_automatico_sdi to impostazioni_azienda

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'm7n8o9p0q1r2'
down_revision = 'l6m7n8o9p0q1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'impostazioni_azienda',
        sa.Column('invio_automatico_sdi', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column('impostazioni_azienda', 'invio_automatico_sdi')
