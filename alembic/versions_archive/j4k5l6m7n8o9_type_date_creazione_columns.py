"""type data_creazione and tracking date columns to Date/DateTime

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-06-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'j4k5l6m7n8o9'
down_revision = 'i3j4k5l6m7n8'
branch_labels = None
depends_on = None

# Colonne da convertire a DATE (nullable)
_DATE_NULLABLE = [
    ("utenti",              "data_registrazione"),
    ("utenti",              "pro_scadenza"),
    ("template_preventivi", "creato_il"),
]

# Colonne da convertire a DATE (not null)
_DATE_NOT_NULL = [
    ("carichi_materiale",   "data_carico"),
    ("movimenti_magazzino", "data_movimento"),
    ("inviti_account",      "scadenza"),
]

# Colonne da convertire a TIMESTAMP (nullable)
_TS_NULLABLE = [
    ("sessioni_lavoro", "fine"),
]

# Colonne da convertire a TIMESTAMP (not null)
_TS_NOT_NULL = [
    ("clienti",                "data_creazione"),
    ("lavori",                 "data_creazione"),
    ("fornitori",              "data_creazione"),
    ("materiali",              "data_creazione"),
    ("materiali_usati_lavoro", "data_creazione"),
    ("documenti_pdf",          "data_creazione"),
    ("foto_lavori",            "data_creazione"),
    ("pagamenti_lavoro",       "data_creazione"),
    ("allegati_lavoro",        "data_creazione"),
    ("fatture_emesse",         "data_creazione"),
    ("sessioni_lavoro",        "inizio"),
    ("garanzie",               "data_creazione"),
    ("prima_nota",             "data_creazione"),
    ("listino_voci",           "data_creazione"),
    ("sal_lavoro",             "data_creazione"),
    ("rapportini_lavoro",      "data_creazione"),
    ("promemoria_clienti",     "data_creazione"),
    ("timesheet_collab",       "data_creazione"),
    ("push_subscriptions",     "creata_il"),
    ("inviti_account",         "data_creazione"),
]


def upgrade() -> None:
    from sqlalchemy import inspect as _inspect
    conn = op.get_bind()
    dialect = conn.dialect.name
    insp = _inspect(conn)
    existing = set(insp.get_table_names())

    def _has_col(table, col):
        return table in existing and any(
            c["name"] == col for c in insp.get_columns(table)
        )

    if dialect == "postgresql":
        # Sanifica prima del cast
        for table, col in _DATE_NOT_NULL + _TS_NOT_NULL:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(
                f"UPDATE {table} SET {col} = '2000-01-01' WHERE {col} IS NULL OR {col} = ''"
            ))
        for table, col in _DATE_NULLABLE + _TS_NULLABLE:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(f"UPDATE {table} SET {col} = NULL WHERE {col} = ''"))

        for table, col in _DATE_NULLABLE:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE DATE"
                f" USING NULLIF({col}, '')::date"
            ))
        for table, col in _DATE_NOT_NULL:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE DATE USING {col}::date"
            ))
        for table, col in _TS_NULLABLE:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMP WITHOUT TIME ZONE"
                f" USING NULLIF({col}, '')::timestamp"
            ))
        for table, col in _TS_NOT_NULL:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {col}"
                f" TYPE TIMESTAMP WITHOUT TIME ZONE USING {col}::timestamp"
            ))

    else:
        # SQLite: batch_alter_table ricostruisce la tabella
        for table, col in _DATE_NOT_NULL + _TS_NOT_NULL:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(
                f"UPDATE {table} SET {col} = '2000-01-01' WHERE {col} IS NULL OR {col} = ''"
            ))

        for table, col in _DATE_NULLABLE:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(f"UPDATE {table} SET {col} = NULL WHERE {col} = ''"))
            with op.batch_alter_table(table) as bop:
                bop.alter_column(col, type_=sa.Date(),
                                 existing_type=sa.String(), existing_nullable=True)

        for table, col in _DATE_NOT_NULL:
            if not _has_col(table, col):
                continue
            with op.batch_alter_table(table) as bop:
                bop.alter_column(col, type_=sa.Date(),
                                 existing_type=sa.String(), existing_nullable=False)

        for table, col in _TS_NULLABLE:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(f"UPDATE {table} SET {col} = NULL WHERE {col} = ''"))
            with op.batch_alter_table(table) as bop:
                bop.alter_column(col, type_=sa.DateTime(),
                                 existing_type=sa.String(), existing_nullable=True)

        for table, col in _TS_NOT_NULL:
            if not _has_col(table, col):
                continue
            with op.batch_alter_table(table) as bop:
                bop.alter_column(col, type_=sa.DateTime(),
                                 existing_type=sa.String(), existing_nullable=False)


def downgrade() -> None:
    from sqlalchemy import inspect as _inspect
    conn = op.get_bind()
    dialect = conn.dialect.name
    insp = _inspect(conn)
    existing = set(insp.get_table_names())

    def _has_col(table, col):
        return table in existing and any(
            c["name"] == col for c in insp.get_columns(table)
        )

    if dialect == "postgresql":
        for table, col in _DATE_NULLABLE + _DATE_NOT_NULL:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR USING {col}::text"
            ))
        for table, col in _TS_NULLABLE + _TS_NOT_NULL:
            if not _has_col(table, col):
                continue
            conn.execute(sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR USING {col}::text"
            ))
    else:
        for table, col in _DATE_NULLABLE:
            if not _has_col(table, col):
                continue
            with op.batch_alter_table(table) as bop:
                bop.alter_column(col, type_=sa.String(),
                                 existing_type=sa.Date(), existing_nullable=True)
        for table, col in _DATE_NOT_NULL:
            if not _has_col(table, col):
                continue
            with op.batch_alter_table(table) as bop:
                bop.alter_column(col, type_=sa.String(),
                                 existing_type=sa.Date(), existing_nullable=False)
        for table, col in _TS_NULLABLE:
            if not _has_col(table, col):
                continue
            with op.batch_alter_table(table) as bop:
                bop.alter_column(col, type_=sa.String(),
                                 existing_type=sa.DateTime(), existing_nullable=True)
        for table, col in _TS_NOT_NULL:
            if not _has_col(table, col):
                continue
            with op.batch_alter_table(table) as bop:
                bop.alter_column(col, type_=sa.String(),
                                 existing_type=sa.DateTime(), existing_nullable=False)
