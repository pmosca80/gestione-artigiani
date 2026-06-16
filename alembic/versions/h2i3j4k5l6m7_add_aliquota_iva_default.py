"""add aliquota_iva_default to impostazioni_azienda

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'h2i3j4k5l6m7'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "impostazioni_azienda",
        sa.Column("aliquota_iva_default", sa.Float(), nullable=True, server_default="22"),
    )


def downgrade():
    op.drop_column("impostazioni_azienda", "aliquota_iva_default")
