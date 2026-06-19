"""add assegnato_a_id to lavori (scoping collaboratori)

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'n8o9p0q1r2s3'
down_revision = 'm7n8o9p0q1r2'
branch_labels = None
depends_on = None


def upgrade():
    # batch_alter_table: su SQLite usa la strategia copy-and-move (necessaria
    # per aggiungere un FK, non supportato da ALTER diretto), su Postgres
    # esegue le stesse operazioni come ALTER normali — sicuro su entrambi.
    with op.batch_alter_table('lavori') as batch_op:
        batch_op.add_column(sa.Column('assegnato_a_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_lavori_assegnato_a_id', 'utenti', ['assegnato_a_id'], ['id']
        )


def downgrade():
    with op.batch_alter_table('lavori') as batch_op:
        batch_op.drop_constraint('fk_lavori_assegnato_a_id', type_='foreignkey')
        batch_op.drop_column('assegnato_a_id')
