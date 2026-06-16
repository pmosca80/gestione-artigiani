"""add totp_secret and totp_abilitato to utenti

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'i3j4k5l6m7n8'
down_revision = 'h2i3j4k5l6m7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "utenti",
        sa.Column("totp_secret", sa.String(), nullable=True),
    )
    op.add_column(
        "utenti",
        sa.Column("totp_abilitato", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("utenti", "totp_abilitato")
    op.drop_column("utenti", "totp_secret")
