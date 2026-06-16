"""Aggiunge tabella audit_log per tracciabilità operazioni fiscali.

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
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR NOT NULL,
                utente_id INTEGER NOT NULL,
                attore_id INTEGER NOT NULL,
                attore_username VARCHAR NOT NULL,
                azione VARCHAR NOT NULL,
                tabella VARCHAR NOT NULL,
                record_id INTEGER,
                dettaglio TEXT,
                ip VARCHAR
            )
        """))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_audit_log_utente_ts ON audit_log (utente_id, timestamp)"
        ))
    else:
        tables = [r[0] for r in conn.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ))]
        if "audit_log" not in tables:
            conn.execute(sa.text("""
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp VARCHAR NOT NULL,
                    utente_id INTEGER NOT NULL,
                    attore_id INTEGER NOT NULL,
                    attore_username VARCHAR NOT NULL,
                    azione VARCHAR NOT NULL,
                    tabella VARCHAR NOT NULL,
                    record_id INTEGER,
                    dettaglio TEXT,
                    ip VARCHAR
                )
            """))
            conn.execute(sa.text(
                "CREATE INDEX ix_audit_log_utente_ts ON audit_log (utente_id, timestamp)"
            ))


def downgrade():
    op.drop_table("audit_log")
