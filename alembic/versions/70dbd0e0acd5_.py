"""empty message

Revision ID: 70dbd0e0acd5
Revises: 9a7f6b4c3d21
Create Date: 2026-05-13 23:33:02.599568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70dbd0e0acd5'
down_revision: Union[str, None] = '9a7f6b4c3d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
