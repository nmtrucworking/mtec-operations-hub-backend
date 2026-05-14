"""Merge multiple migration heads

Revision ID: 9dcf6450482f
Revises: 002_add_minutes_url, c4f2b5f0a2b1
Create Date: 2026-05-14 19:11:52.701681

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9dcf6450482f'
down_revision: Union[str, None] = ('002_add_minutes_url', 'c4f2b5f0a2b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
