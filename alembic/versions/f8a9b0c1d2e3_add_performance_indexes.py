"""Indici di performance: utente_id su tabelle principali + lookup unici.

Revision ID: f8a9b0c1d2e3
Revises: e6f7a8b9c0d1
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'f8a9b0c1d2e3'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name  # 'postgresql' o 'sqlite'

    _create_if_not_exists = _pg_create if dialect == "postgresql" else _sqlite_create

    # ── lavori ────────────────────────────────────────────────────────────────
    # Ogni route filtra lavori per utente; il filtro su stato è frequente
    _create_if_not_exists(conn, "ix_lavori_utente_id",
                          "CREATE INDEX ix_lavori_utente_id ON lavori (utente_id)")
    _create_if_not_exists(conn, "ix_lavori_utente_stato",
                          "CREATE INDEX ix_lavori_utente_stato ON lavori (utente_id, stato)")
    _create_if_not_exists(conn, "ix_lavori_utente_stato_fattura",
                          "CREATE INDEX ix_lavori_utente_stato_fattura ON lavori (utente_id, stato_fattura)")
    _create_if_not_exists(conn, "ix_lavori_cliente_id",
                          "CREATE INDEX ix_lavori_cliente_id ON lavori (cliente_id)")
    # Lookup univoci per portale firma — ricercati per token
    _create_if_not_exists(conn, "ix_lavori_token_firma",
                          "CREATE UNIQUE INDEX ix_lavori_token_firma ON lavori (token_firma) "
                          "WHERE token_firma IS NOT NULL")

    # ── clienti ───────────────────────────────────────────────────────────────
    _create_if_not_exists(conn, "ix_clienti_utente_id",
                          "CREATE INDEX ix_clienti_utente_id ON clienti (utente_id)")
    _create_if_not_exists(conn, "ix_clienti_token_portale",
                          "CREATE UNIQUE INDEX ix_clienti_token_portale ON clienti (token_portale) "
                          "WHERE token_portale IS NOT NULL")

    # ── materiali ─────────────────────────────────────────────────────────────
    _create_if_not_exists(conn, "ix_materiali_utente_id",
                          "CREATE INDEX ix_materiali_utente_id ON materiali (utente_id)")

    # ── fatture_emesse ────────────────────────────────────────────────────────
    # Registro fatture filtra per (utente_id, anno)
    _create_if_not_exists(conn, "ix_fatture_emesse_utente_id",
                          "CREATE INDEX ix_fatture_emesse_utente_id ON fatture_emesse (utente_id)")
    _create_if_not_exists(conn, "ix_fatture_emesse_utente_anno",
                          "CREATE INDEX ix_fatture_emesse_utente_anno ON fatture_emesse (utente_id, anno)")

    # ── voci_preventivo ───────────────────────────────────────────────────────
    # Joinata spesso con lavori; tenant-scoped
    _create_if_not_exists(conn, "ix_voci_preventivo_lavoro_id",
                          "CREATE INDEX ix_voci_preventivo_lavoro_id ON voci_preventivo (lavoro_id)")
    _create_if_not_exists(conn, "ix_voci_preventivo_utente_id",
                          "CREATE INDEX ix_voci_preventivo_utente_id ON voci_preventivo (utente_id)")

    # ── prima_nota ────────────────────────────────────────────────────────────
    _create_if_not_exists(conn, "ix_prima_nota_utente_id",
                          "CREATE INDEX ix_prima_nota_utente_id ON prima_nota (utente_id)")

    # ── promemoria_clienti ────────────────────────────────────────────────────
    _create_if_not_exists(conn, "ix_promemoria_utente_id",
                          "CREATE INDEX ix_promemoria_utente_id ON promemoria_clienti (utente_id)")

    # ── garanzie ─────────────────────────────────────────────────────────────
    _create_if_not_exists(conn, "ix_garanzie_utente_id",
                          "CREATE INDEX ix_garanzie_utente_id ON garanzie (utente_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_lavori_utente_id")
    op.execute("DROP INDEX IF EXISTS ix_lavori_utente_stato")
    op.execute("DROP INDEX IF EXISTS ix_lavori_utente_stato_fattura")
    op.execute("DROP INDEX IF EXISTS ix_lavori_cliente_id")
    op.execute("DROP INDEX IF EXISTS ix_lavori_token_firma")
    op.execute("DROP INDEX IF EXISTS ix_clienti_utente_id")
    op.execute("DROP INDEX IF EXISTS ix_clienti_token_portale")
    op.execute("DROP INDEX IF EXISTS ix_materiali_utente_id")
    op.execute("DROP INDEX IF EXISTS ix_fatture_emesse_utente_id")
    op.execute("DROP INDEX IF EXISTS ix_fatture_emesse_utente_anno")
    op.execute("DROP INDEX IF EXISTS ix_voci_preventivo_lavoro_id")
    op.execute("DROP INDEX IF EXISTS ix_voci_preventivo_utente_id")
    op.execute("DROP INDEX IF EXISTS ix_prima_nota_utente_id")
    op.execute("DROP INDEX IF EXISTS ix_promemoria_utente_id")
    op.execute("DROP INDEX IF EXISTS ix_garanzie_utente_id")


# ── helper ────────────────────────────────────────────────────────────────────

def _pg_create(conn, index_name: str, ddl: str):
    """PostgreSQL: salta se l'indice esiste già."""
    exists = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": index_name}
    ).scalar()
    if not exists:
        # Le UNIQUE ... WHERE non si possono creare IF NOT EXISTS su PG < 15
        conn.execute(sa.text(ddl))


def _sqlite_create(conn, index_name: str, ddl: str):
    """SQLite: aggiunge IF NOT EXISTS al DDL."""
    safe_ddl = ddl
    if "IF NOT EXISTS" not in safe_ddl:
        # Inserisci IF NOT EXISTS dopo la prima occorrenza di "INDEX "
        safe_ddl = safe_ddl.replace("INDEX ", "INDEX IF NOT EXISTS ", 1)
    conn.execute(sa.text(safe_ddl))
