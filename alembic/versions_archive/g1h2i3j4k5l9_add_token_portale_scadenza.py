"""clienti: aggiungi token_portale_scadenza

Revision ID: g1h2i3j4k5l9
Revises: g1h2i3j4k5l6
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'g1h2i3j4k5l9'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clienti",
        sa.Column("token_portale_scadenza", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("clienti", "token_portale_scadenza")
