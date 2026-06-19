"""Aggiunge importo_bollo a fatture_emesse per tracciare la marca da bollo virtuale.

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
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        conn.execute(sa.text(
            "ALTER TABLE fatture_emesse ADD COLUMN IF NOT EXISTS importo_bollo FLOAT DEFAULT 0"
        ))
    else:
        cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(fatture_emesse)"))]
        if "importo_bollo" not in cols:
            conn.execute(sa.text(
                "ALTER TABLE fatture_emesse ADD COLUMN importo_bollo FLOAT DEFAULT 0"
            ))


def downgrade():
    pass
