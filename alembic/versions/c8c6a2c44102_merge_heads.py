"""merge heads

Revision ID: c8c6a2c44102
Revises: 6b149d956181, b7c8d9e0f1a2
Create Date: 2026-06-03 18:17:11.973710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8c6a2c44102'
down_revision: Union[str, None] = ('6b149d956181', 'b7c8d9e0f1a2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
