"""prima_nota: aggiungi lavoro_id e cliente_id FK

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7a8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("prima_nota",
        sa.Column("lavoro_id", sa.Integer(),
                  sa.ForeignKey("lavori.id"), nullable=True))
    op.add_column("prima_nota",
        sa.Column("cliente_id", sa.Integer(),
                  sa.ForeignKey("clienti.id"), nullable=True))


def downgrade():
    op.drop_column("prima_nota", "cliente_id")
    op.drop_column("prima_nota", "lavoro_id")
