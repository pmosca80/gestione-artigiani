"""convert date string columns to DATE type

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None

# Colonne nullable: usa NULLIF per gestire stringhe vuote
_NULLABLE = [
    ("lavori",           "data_fattura"),
    ("lavori",           "data_scadenza_pagamento"),
    ("lavori",           "data_invio_preventivo"),
    ("lavori",           "data_accettazione_preventivo"),
]

# Colonne NOT NULL: sanifica prima, poi converti
_NOT_NULL = [
    ("lavori",           "data_lavoro"),
    ("fatture_emesse",   "data_emissione"),
    ("pagamenti_lavoro", "data_pagamento"),
    ("garanzie",         "data_installazione"),
    ("garanzie",         "data_scadenza"),
    ("prima_nota",       "data"),
    ("sal_lavoro",       "data"),
    ("rapportini_lavoro","data"),
    ("timesheet_collab", "data"),
    ("promemoria_clienti","data_promemoria"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Sanifica valori NULL/vuoti nelle colonne NOT NULL prima del cast
    for table, col in _NOT_NULL:
        conn.execute(sa.text(
            f"UPDATE {table} SET {col} = '2000-01-01'"
            f" WHERE {col} IS NULL OR {col} = ''"
        ))

    # Converti colonne NOT NULL
    for table, col in _NOT_NULL:
        op.alter_column(
            table, col,
            type_=sa.Date(),
            postgresql_using=f"{col}::date",
            existing_nullable=False,
        )

    # Converti colonne nullable (stringhe vuote → NULL)
    for table, col in _NULLABLE:
        conn.execute(sa.text(
            f"UPDATE {table} SET {col} = NULL WHERE {col} = ''"
        ))
        op.alter_column(
            table, col,
            type_=sa.Date(),
            postgresql_using=f"NULLIF({col}, '')::date",
            existing_nullable=True,
        )


def downgrade() -> None:
    for table, col in _NOT_NULL:
        op.alter_column(
            table, col,
            type_=sa.String(),
            postgresql_using=f"{col}::text",
            existing_nullable=False,
        )
    for table, col in _NULLABLE:
        op.alter_column(
            table, col,
            type_=sa.String(),
            postgresql_using=f"{col}::text",
            existing_nullable=True,
        )
