"""clienti: aggiungi token_portale_scadenza

Revision ID: g1h2i3j4k5l6
Revises: f8a9b0c1d2e3
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'g1h2i3j4k5l6'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clienti",
        sa.Column("token_portale_scadenza", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("clienti", "token_portale_scadenza")
