"""add student_id to users

Revision ID: a1b2c3d4e5f6
Revises: f9a8b7c6d5e4
Create Date: 2026-06-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f9a8b7c6d5e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = inspector.get_columns(table_name)
    return any(c.get("name") == column_name for c in cols)


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def upgrade() -> None:
    # add student_id column and unique index if not present
    if not _column_exists("users", "student_id"):
        op.add_column("users", sa.Column("student_id", sa.String(length=20), nullable=True))
    if not _index_exists("users", "ix_users_student_id"):
        op.create_index("ix_users_student_id", "users", ["student_id"], unique=True)


def downgrade() -> None:
    # remove index and column if present
    if _index_exists("users", "ix_users_student_id"):
        op.drop_index("ix_users_student_id", table_name="users")
    if _column_exists("users", "student_id"):
        op.drop_column("users", "student_id")
