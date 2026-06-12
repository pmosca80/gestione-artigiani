"""add ultimo_anno_fattura

Revision ID: d4e5f6a7b8c9
Revises: c3a1f9e2d8b7
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3a1f9e2d8b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('impostazioni_azienda', sa.Column('ultimo_anno_fattura', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('impostazioni_azienda', 'ultimo_anno_fattura')
