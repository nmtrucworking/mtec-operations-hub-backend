"""merge multiple heads

Revision ID: c6bbfbf36a67
Revises: 67a61dcf0e2d, f9a8b7c6d5e4
Create Date: 2026-06-01 00:04:32.098564

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6bbfbf36a67'
down_revision: Union[str, None] = ('67a61dcf0e2d', 'f9a8b7c6d5e4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
