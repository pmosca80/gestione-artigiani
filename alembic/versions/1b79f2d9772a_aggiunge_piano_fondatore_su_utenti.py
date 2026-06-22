"""aggiunge piano_fondatore su utenti

Revision ID: 1b79f2d9772a
Revises: 09a36b6fc538
Create Date: 2026-06-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b79f2d9772a'
down_revision: Union[str, Sequence[str], None] = '09a36b6fc538'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.add_column(sa.Column('piano_fondatore', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.drop_column('piano_fondatore')
