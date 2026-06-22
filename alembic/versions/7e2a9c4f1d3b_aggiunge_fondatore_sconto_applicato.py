"""aggiunge fondatore_sconto_applicato su utenti

Revision ID: 7e2a9c4f1d3b
Revises: 1b79f2d9772a
Create Date: 2026-06-22 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e2a9c4f1d3b'
down_revision: Union[str, Sequence[str], None] = '1b79f2d9772a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fondatore_sconto_applicato', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.drop_column('fondatore_sconto_applicato')
