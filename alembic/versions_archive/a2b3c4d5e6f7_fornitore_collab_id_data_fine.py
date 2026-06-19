"""fornitore model, collaboratore_id timesheet, data_fine_prevista lavoro

Revision ID: a2b3c4d5e6f7
Revises: f7a8b9c0d1e2
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'a2b3c4d5e6f7'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    # Tabella fornitori
    op.create_table(
        "fornitori",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("utente_id", sa.Integer(), sa.ForeignKey("utenti.id"), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("partita_iva", sa.String(), nullable=True),
        sa.Column("codice_fiscale", sa.String(), nullable=True),
        sa.Column("telefono", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("indirizzo", sa.String(), nullable=True),
        sa.Column("citta", sa.String(), nullable=True),
        sa.Column("provincia", sa.String(), nullable=True),
        sa.Column("cap", sa.String(), nullable=True),
        sa.Column("sito_web", sa.String(), nullable=True),
        sa.Column("categoria", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("data_creazione", sa.String(), nullable=False),
        sa.Column("data_aggiornamento", sa.DateTime(timezone=True),
                  nullable=True, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fornitori_id", "fornitori", ["id"])

    # FK fornitore_id su materiali e prima_nota
    op.add_column("materiali",
        sa.Column("fornitore_id", sa.Integer(),
                  sa.ForeignKey("fornitori.id"), nullable=True))

    op.add_column("prima_nota",
        sa.Column("fornitore_id", sa.Integer(),
                  sa.ForeignKey("fornitori.id"), nullable=True))

    # FK collaboratore_id su timesheet_collab
    op.add_column("timesheet_collab",
        sa.Column("collaboratore_id", sa.Integer(),
                  sa.ForeignKey("utenti.id"), nullable=True))

    # data_fine_prevista su lavori
    op.add_column("lavori",
        sa.Column("data_fine_prevista", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("lavori", "data_fine_prevista")
    op.drop_column("timesheet_collab", "collaboratore_id")
    op.drop_column("prima_nota", "fornitore_id")
    op.drop_column("materiali", "fornitore_id")
    op.drop_index("ix_fornitori_id", table_name="fornitori")
    op.drop_table("fornitori")
