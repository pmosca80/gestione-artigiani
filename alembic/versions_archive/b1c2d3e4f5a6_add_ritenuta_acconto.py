"""add ritenuta acconto to lavori

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lavori', sa.Column('ritenuta_acconto', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('lavori', sa.Column('aliquota_ritenuta', sa.Float(), nullable=True, server_default='20.0'))


def downgrade() -> None:
    op.drop_column('lavori', 'aliquota_ritenuta')
    op.drop_column('lavori', 'ritenuta_acconto')
