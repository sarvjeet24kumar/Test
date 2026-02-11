"""add cancelled_at resent_at to invites

Revision ID: a1b2c3d4e5f6
Revises: 30cf4da6f2f7
Create Date: 2026-02-11 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '30cf4da6f2f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'shopping_list_invites',
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'shopping_list_invites',
        sa.Column('resent_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('shopping_list_invites', 'resent_at')
    op.drop_column('shopping_list_invites', 'cancelled_at')
