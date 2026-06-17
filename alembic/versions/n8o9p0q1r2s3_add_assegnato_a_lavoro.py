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
    op.add_column('lavori', sa.Column('assegnato_a_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_lavori_assegnato_a_id', 'lavori', 'utenti', ['assegnato_a_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_lavori_assegnato_a_id', 'lavori', type_='foreignkey')
    op.drop_column('lavori', 'assegnato_a_id')
