"""normalize member departments

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-05 11:10:00.000000

"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import column, table

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


DEPARTMENT_LABEL_BY_CODE: dict[str, str] = {
    "BCN": "Ban Chủ nhiệm",
    "BVH": "Ban Vận hành",
    "BCNg": "Ban Công nghệ",
    "BTT": "Ban Truyền thông",
}


def _normalize_text(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )


DEPARTMENT_CODE_BY_ALIAS: dict[str, str] = {
    "bcn": "BCN",
    "ban chu nhiem": "BCN",
    "chu nhiem": "BCN",
    "bvh": "BVH",
    "ban van hanh": "BVH",
    "van hanh": "BVH",
    "bcng": "BCNg",
    "ban cong nghe": "BCNg",
    "cong nghe": "BCNg",
    "btt": "BTT",
    "ban truyen thong": "BTT",
    "truyen thong": "BTT",
}


for code, label in DEPARTMENT_LABEL_BY_CODE.items():
    DEPARTMENT_CODE_BY_ALIAS[_normalize_text(code)] = code
    DEPARTMENT_CODE_BY_ALIAS[_normalize_text(label)] = code


def _normalize_department_codes(value: str | None) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []

    parts = [part.strip() for part in re.split(r"[,;/\n|]+", text) if part.strip()]
    codes: list[str] = []
    for part in parts:
        code = DEPARTMENT_CODE_BY_ALIAS.get(_normalize_text(part))
        if code and code not in codes:
            codes.append(code)
    return codes


def _serialize_department_labels(codes: list[str]) -> str | None:
    labels = [DEPARTMENT_LABEL_BY_CODE[code] for code in codes if code in DEPARTMENT_LABEL_BY_CODE]
    return ", ".join(labels) if labels else None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "member_departments"):
        op.create_table(
            "member_departments",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("department_code", sa.String(length=20), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("member_id", "department_code", name="uq_member_departments_member_code"),
        )
        inspector = sa.inspect(bind)

    if not _has_index(inspector, "member_departments", "ix_member_departments_member_id"):
        op.create_index("ix_member_departments_member_id", "member_departments", ["member_id"], unique=False)
    if not _has_index(inspector, "member_departments", "ix_member_departments_department_code"):
        op.create_index("ix_member_departments_department_code", "member_departments", ["department_code"], unique=False)

    op.alter_column("members", "ban", existing_type=sa.String(length=50), type_=sa.Text(), existing_nullable=True)

    members = bind.execute(sa.text("SELECT id, ban FROM members")).fetchall()
    now = datetime.now(UTC).replace(tzinfo=None)
    member_departments = table(
        "member_departments",
        column("id", sa.String(length=36)),
        column("member_id", sa.String(length=36)),
        column("department_code", sa.String(length=20)),
        column("sort_order", sa.Integer()),
        column("created_at", sa.DateTime()),
    )

    for member_id, ban in members:
        codes = _normalize_department_codes(ban)
        if not codes:
            continue

        existing_codes = {
            row[0]
            for row in bind.execute(
                sa.text("SELECT department_code FROM member_departments WHERE member_id = :member_id"),
                {"member_id": member_id},
            ).fetchall()
        }
        new_codes = [code for code in codes if code not in existing_codes]

        if new_codes:
            op.bulk_insert(
                member_departments,
                [
                    {
                        "id": str(uuid4()),
                        "member_id": member_id,
                        "department_code": code,
                        "sort_order": index,
                        "created_at": now,
                    }
                    for index, code in enumerate(new_codes, start=len(existing_codes))
                ],
            )
        bind.execute(
            sa.text("UPDATE members SET ban = :ban WHERE id = :member_id"),
            {"member_id": member_id, "ban": _serialize_department_labels(codes)},
        )

    op.alter_column("member_departments", "sort_order", server_default=None)


def downgrade() -> None:
    op.alter_column("members", "ban", existing_type=sa.Text(), type_=sa.String(length=50), existing_nullable=True)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, "member_departments"):
        if _has_index(inspector, "member_departments", "ix_member_departments_department_code"):
            op.drop_index("ix_member_departments_department_code", table_name="member_departments")
        if _has_index(inspector, "member_departments", "ix_member_departments_member_id"):
            op.drop_index("ix_member_departments_member_id", table_name="member_departments")
        op.drop_table("member_departments")
