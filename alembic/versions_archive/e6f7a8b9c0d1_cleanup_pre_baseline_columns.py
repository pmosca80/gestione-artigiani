"""Catch-up: colonne e tabelle create da _run_migrations() ma non trackate da Alembic.

Usa ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS: idempotente sul DB
di produzione che ha già queste colonne (aggiunte da _run_migrations()).

Dopo questa migration, _run_migrations() può essere rimossa da main.py.

Revision ID: e6f7a8b9c0d1
Revises: c4d5e6f7a8b9
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6f7a8b9c0d1'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name  # 'postgresql' o 'sqlite'

    # ── utenti ────────────────────────────────────────────────────────────────
    _add_if_not_exists(conn, dialect, "utenti", [
        ("pro_scadenza",    "VARCHAR"),
        ("titolare_id",     "INTEGER"),
        ("ruolo",           "VARCHAR DEFAULT 'titolare'"),
        ("onboarding_done", "BOOLEAN DEFAULT FALSE"),
        ("cal_token",       "VARCHAR"),
    ])

    # ── fatture_emesse ────────────────────────────────────────────────────────
    _add_if_not_exists(conn, dialect, "fatture_emesse", [
        ("reminder_inviato",   "INTEGER DEFAULT 0"),
        ("tipo_documento",     "VARCHAR DEFAULT 'TD01'"),
        ("fattura_rif_numero", "INTEGER"),
        ("fattura_rif_anno",   "INTEGER"),
    ])

    # ── impostazioni_azienda ──────────────────────────────────────────────────
    _add_if_not_exists(conn, dialect, "impostazioni_azienda", [
        ("pec_indirizzo",     "VARCHAR"),
        ("pec_smtp_host",     "VARCHAR"),
        ("pec_smtp_port",     "INTEGER DEFAULT 465"),
        ("pec_smtp_password", "VARCHAR"),
    ])

    # ── clienti ───────────────────────────────────────────────────────────────
    _add_if_not_exists(conn, dialect, "clienti", [
        ("token_portale", "VARCHAR"),
    ])

    # ── lavori ────────────────────────────────────────────────────────────────
    _add_if_not_exists(conn, dialect, "lavori", [
        ("token_firma",        "VARCHAR"),
        ("firma_nome_cliente", "VARCHAR"),
        ("firma_ip",           "VARCHAR"),
    ])

    # ── tabelle create da _run_migrations() non ancora in Alembic ────────────
    insp = sa.inspect(conn)

    if not insp.has_table("template_preventivi"):
        op.create_table(
            "template_preventivi",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("utente_id", sa.Integer(), sa.ForeignKey("utenti.id"), nullable=False),
            sa.Column("nome", sa.String(), nullable=False),
            sa.Column("titolo", sa.String(), server_default=""),
            sa.Column("descrizione", sa.Text(), server_default=""),
            sa.Column("importo_preventivato", sa.Float(), server_default="0"),
            sa.Column("aliquota_iva", sa.Float(), server_default="22"),
            sa.Column("sconto", sa.Float(), server_default="0"),
            sa.Column("note_consuntivo", sa.Text(), server_default=""),
            sa.Column("creato_il", sa.String()),
        )

    if not insp.has_table("listino_voci"):
        op.create_table(
            "listino_voci",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("utente_id", sa.Integer(), sa.ForeignKey("utenti.id"), nullable=False),
            sa.Column("descrizione", sa.String(), nullable=False),
            sa.Column("unita_misura", sa.String(), server_default=""),
            sa.Column("prezzo_unitario", sa.Float(), server_default="0"),
            sa.Column("categoria", sa.String(), server_default=""),
            sa.Column("data_creazione", sa.String(), nullable=False),
        )

    if not insp.has_table("sal_lavoro"):
        op.create_table(
            "sal_lavoro",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("lavoro_id", sa.Integer(), sa.ForeignKey("lavori.id"), nullable=False),
            sa.Column("utente_id", sa.Integer(), sa.ForeignKey("utenti.id"), nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("data", sa.String(), nullable=False),
            sa.Column("percentuale", sa.Float(), nullable=False, server_default="0"),
            sa.Column("importo_richiesto", sa.Float(), nullable=False, server_default="0"),
            sa.Column("descrizione", sa.Text(), server_default=""),
            sa.Column("note", sa.Text(), server_default=""),
            sa.Column("stato", sa.String(), nullable=False, server_default="emesso"),
            sa.Column("data_creazione", sa.String(), nullable=False),
        )

    if not insp.has_table("rapportini_lavoro"):
        op.create_table(
            "rapportini_lavoro",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("lavoro_id", sa.Integer(), sa.ForeignKey("lavori.id"), nullable=False),
            sa.Column("utente_id", sa.Integer(), sa.ForeignKey("utenti.id"), nullable=False),
            sa.Column("data", sa.String(), nullable=False),
            sa.Column("ore_lavorate", sa.Float(), server_default="0"),
            sa.Column("descrizione_attivita", sa.Text(), nullable=False),
            sa.Column("materiali_note", sa.Text(), server_default=""),
            sa.Column("note", sa.Text(), server_default=""),
            sa.Column("data_creazione", sa.String(), nullable=False),
        )

    if not insp.has_table("promemoria_clienti"):
        op.create_table(
            "promemoria_clienti",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("utente_id", sa.Integer(), sa.ForeignKey("utenti.id"), nullable=False),
            sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clienti.id"), nullable=True),
            sa.Column("titolo", sa.String(), nullable=False),
            sa.Column("note", sa.Text(), server_default=""),
            sa.Column("data_promemoria", sa.String(), nullable=False),
            sa.Column("tipo", sa.String(), nullable=False, server_default="manutenzione"),
            sa.Column("stato", sa.String(), nullable=False, server_default="attivo"),
            sa.Column("data_creazione", sa.String(), nullable=False),
        )

    if not insp.has_table("timesheet_collab"):
        op.create_table(
            "timesheet_collab",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("lavoro_id", sa.Integer(), sa.ForeignKey("lavori.id"), nullable=False),
            sa.Column("utente_id", sa.Integer(), sa.ForeignKey("utenti.id"), nullable=False),
            sa.Column("nome_operaio", sa.String(), nullable=False),
            sa.Column("data", sa.String(), nullable=False),
            sa.Column("ore", sa.Float(), nullable=False, server_default="0"),
            sa.Column("costo_orario", sa.Float(), server_default="0"),
            sa.Column("note", sa.Text(), server_default=""),
            sa.Column("data_creazione", sa.String(), nullable=False),
        )

    # Fix dati: residuo non può essere negativo
    conn.execute(sa.text(
        "UPDATE lavori SET residuo_pagamento = 0 WHERE residuo_pagamento < 0"
    ))


def downgrade():
    # Le colonne pre-baseline erano presenti prima di Alembic:
    # il downgrade le eliminerebbe rompendo l'app — non implementato intenzionalmente.
    pass


# ── helper ────────────────────────────────────────────────────────────────────

def _add_if_not_exists(conn, dialect: str, table: str, columns: list[tuple]):
    """Aggiunge colonne solo se non esistono già (idempotente)."""
    if dialect == "postgresql":
        for col_name, col_def in columns:
            conn.execute(sa.text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
            ))
    else:
        # SQLite: controlla manualmente prima di ALTER TABLE
        insp = sa.inspect(conn)
        existing = {c["name"] for c in insp.get_columns(table)}
        for col_name, col_def in columns:
            if col_name not in existing:
                conn.execute(sa.text(
                    f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
                ))
