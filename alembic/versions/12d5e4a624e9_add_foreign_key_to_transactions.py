"""add_foreign_key_to_transactions

Revision ID: 12d5e4a624e9
Revises: 001_initial
Create Date: 2026-04-29 00:55:58.597206

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '12d5e4a624e9'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
