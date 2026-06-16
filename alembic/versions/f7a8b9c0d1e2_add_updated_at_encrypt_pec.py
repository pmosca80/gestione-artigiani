"""add data_aggiornamento + encrypt pec_smtp_password

Revision ID: f7a8b9c0d1e2
Revises: e4f5a6b7c8d9
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'f7a8b9c0d1e2'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None

# Tabelle che ricevono data_aggiornamento
_TABLES = [
    "utenti",
    "clienti",
    "lavori",
    "materiali",
    "impostazioni_azienda",
    "fatture_emesse",
    "garanzie",
    "prima_nota",
    "listino_voci",
    "sal_lavoro",
    "rapportini_lavoro",
    "promemoria_clienti",
    "timesheet_collab",
    "voci_preventivo",
    "template_preventivi",
]


def upgrade():
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "data_aggiornamento",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.func.now(),
            ),
        )


def downgrade():
    for table in _TABLES:
        op.drop_column(table, "data_aggiornamento")
