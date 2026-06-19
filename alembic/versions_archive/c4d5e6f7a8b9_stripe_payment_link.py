"""fatture_emesse: aggiungi stripe_payment_link_id e stripe_payment_link_url

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fatture_emesse",
        sa.Column("stripe_payment_link_id", sa.String(), nullable=True))
    op.add_column("fatture_emesse",
        sa.Column("stripe_payment_link_url", sa.String(), nullable=True))


def downgrade():
    op.drop_column("fatture_emesse", "stripe_payment_link_url")
    op.drop_column("fatture_emesse", "stripe_payment_link_id")
