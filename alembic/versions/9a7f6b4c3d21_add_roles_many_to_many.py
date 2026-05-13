"""add_roles_many_to_many

Revision ID: 9a7f6b4c3d21
Revises: 12d5e4a624e9
Create Date: 2026-05-13 10:00:00.000000

"""

from datetime import UTC, datetime
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a7f6b4c3d21"
down_revision: Union[str, None] = "12d5e4a624e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_NAMES = [
    "bcn",
    "bvh_finance",
    "bvh_logistics",
    "bvh_discipline",
    "bvh_hr",
    "bcm",
    "member",
]


def _uuid() -> str:
    return str(uuid4())


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=True)

    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )
    op.create_index(op.f("ix_user_roles_role_id"), "user_roles", ["role_id"], unique=False)
    op.create_index(op.f("ix_user_roles_user_id"), "user_roles", ["user_id"], unique=False)

    conn = op.get_bind()
    now = datetime.now(UTC)

    role_ids: dict[str, str] = {}
    for role_name in ROLE_NAMES:
        role_id = _uuid()
        role_ids[role_name] = role_id
        conn.execute(
            sa.text("INSERT INTO roles (id, name) VALUES (:id, :name)"),
            {"id": role_id, "name": role_name},
        )

    rows = conn.execute(sa.text("SELECT id, role FROM users")).fetchall()
    for row in rows:
        role_name = row.role or "member"
        if role_name not in role_ids:
            role_id = _uuid()
            role_ids[role_name] = role_id
            conn.execute(
                sa.text("INSERT INTO roles (id, name) VALUES (:id, :name)"),
                {"id": role_id, "name": role_name},
            )

        conn.execute(
            sa.text(
                """
                INSERT INTO user_roles (id, user_id, role_id, created_at)
                VALUES (:id, :user_id, :role_id, :created_at)
                """
            ),
            {
                "id": _uuid(),
                "user_id": row.id,
                "role_id": role_ids[role_name],
                "created_at": now,
            },
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_roles_user_id"), table_name="user_roles")
    op.drop_index(op.f("ix_user_roles_role_id"), table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
