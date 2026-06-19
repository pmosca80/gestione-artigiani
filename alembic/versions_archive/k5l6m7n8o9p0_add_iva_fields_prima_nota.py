"""add aliquota_iva and importo_iva to prima_nota

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-06-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'k5l6m7n8o9p0'
down_revision = 'j4k5l6m7n8o9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('prima_nota', sa.Column('aliquota_iva', sa.Float(), nullable=True, server_default='0'))
    op.add_column('prima_nota', sa.Column('importo_iva', sa.Float(), nullable=True, server_default='0'))


def downgrade():
    op.drop_column('prima_nota', 'importo_iva')
    op.drop_column('prima_nota', 'aliquota_iva')
