"""add avatar url to users

Revision ID: d4e5f6a7b8c9
Revises: c8c6a2c44102
Create Date: 2026-06-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c8c6a2c44102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(length=1000), nullable=True))
    op.add_column("users", sa.Column("avatar_source", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_source")
    op.drop_column("users", "avatar_url")
