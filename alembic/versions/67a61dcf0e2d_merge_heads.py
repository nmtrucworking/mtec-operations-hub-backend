"""merge heads

Revision ID: 67a61dcf0e2d
Revises: e3b7c9a4d012, ea5b2c1f4a6f
Create Date: 2026-05-22 22:55:38.019404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67a61dcf0e2d'
down_revision: Union[str, None] = ('e3b7c9a4d012', 'ea5b2c1f4a6f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
