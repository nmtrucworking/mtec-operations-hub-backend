"""merge heads

Revision ID: 6b149d956181
Revises: a1b2c3d4e5f6, c6bbfbf36a67
Create Date: 2026-06-01 15:56:07.335075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b149d956181'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'c6bbfbf36a67')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
