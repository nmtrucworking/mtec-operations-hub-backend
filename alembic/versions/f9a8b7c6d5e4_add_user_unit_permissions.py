"""add user unit permissions

Revision ID: f9a8b7c6d5e4
Revises: d2a1f7e9b001
Create Date: 2026-05-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9a8b7c6d5e4"
down_revision: str | None = "d2a1f7e9b001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def _create_index(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index(table_name: str, index_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _table_exists("user_unit_permissions"):
        op.create_table(
            "user_unit_permissions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("unit_code", sa.String(length=30), nullable=False),
            sa.Column("permission_role", sa.String(length=50), nullable=False),
            sa.Column("can_view_unit_results", sa.Boolean(), nullable=False),
            sa.Column("can_score_component_ii", sa.Boolean(), nullable=False),
            sa.Column("can_score_component_iii_a", sa.Boolean(), nullable=False),
            sa.Column("can_score_component_iii_b", sa.Boolean(), nullable=False),
            sa.Column("can_submit_evidence", sa.Boolean(), nullable=False),
            sa.Column("can_verify_evidence", sa.Boolean(), nullable=False),
            sa.Column("can_review_appeal", sa.Boolean(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("starts_at", sa.DateTime(), nullable=True),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id",
                "unit_code",
                "permission_role",
                name="uq_user_unit_permissions_user_unit_role",
            ),
        )
    _create_index("user_unit_permissions", "ix_user_unit_permissions_user_id", ["user_id"])
    _create_index("user_unit_permissions", "ix_user_unit_permissions_unit_code", ["unit_code"])
    _create_index("user_unit_permissions", "ix_user_unit_permissions_permission_role", ["permission_role"])
    _create_index("user_unit_permissions", "ix_user_unit_permissions_is_active", ["is_active"])


def downgrade() -> None:
    if _table_exists("user_unit_permissions"):
        _drop_index("user_unit_permissions", "ix_user_unit_permissions_is_active")
        _drop_index("user_unit_permissions", "ix_user_unit_permissions_permission_role")
        _drop_index("user_unit_permissions", "ix_user_unit_permissions_unit_code")
        _drop_index("user_unit_permissions", "ix_user_unit_permissions_user_id")
        op.drop_table("user_unit_permissions")
