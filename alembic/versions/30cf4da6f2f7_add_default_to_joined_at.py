"""add default to joined_at

Revision ID: 30cf4da6f2f7
Revises: b1d3fa8454a1
Create Date: 2026-02-11 10:56:16.197018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30cf4da6f2f7'
down_revision: Union[str, None] = 'b1d3fa8454a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
