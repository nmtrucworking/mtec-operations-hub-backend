"""add_activity_tables

Revision ID: c4f2b5f0a2b1
Revises: 70dbd0e0acd5
Create Date: 2026-05-14 10:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f2b5f0a2b1"
down_revision: Union[str, None] = "70dbd0e0acd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def upgrade() -> None:
    if not _table_exists("competitions"):
        op.create_table(
            "competitions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("scale", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists("competitions", "ix_competitions_title"):
        op.create_index("ix_competitions_title", "competitions", ["title"], unique=False)

    if not _table_exists("meetings"):
        op.create_table(
            "meetings",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("date", sa.DateTime(), nullable=False),
            sa.Column("meeting_type", sa.String(length=50), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists("meetings", "ix_meetings_title"):
        op.create_index("ix_meetings_title", "meetings", ["title"], unique=False)

    if not _index_exists("meetings", "ix_meetings_meeting_type"):
        op.create_index("ix_meetings_meeting_type", "meetings", ["meeting_type"], unique=False)

    if not _table_exists("competition_results"):
        op.create_table(
            "competition_results",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("competition_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("achievement", sa.String(length=100), nullable=False),
            sa.Column("bonus_kpi", sa.Float(), nullable=False),
            sa.Column("is_synced", sa.Boolean(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists("competition_results", "ix_competition_results_competition_id"):
        op.create_index(
            "ix_competition_results_competition_id",
            "competition_results",
            ["competition_id"],
            unique=False,
        )

    if not _index_exists("competition_results", "ix_competition_results_member_id"):
        op.create_index(
            "ix_competition_results_member_id",
            "competition_results",
            ["member_id"],
            unique=False,
        )

    if not _table_exists("attendances"):
        op.create_table(
            "attendances",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("meeting_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists("attendances", "ix_attendances_meeting_id"):
        op.create_index("ix_attendances_meeting_id", "attendances", ["meeting_id"], unique=False)

    if not _index_exists("attendances", "ix_attendances_member_id"):
        op.create_index("ix_attendances_member_id", "attendances", ["member_id"], unique=False)


def downgrade() -> None:
    if _index_exists("attendances", "ix_attendances_member_id"):
        op.drop_index("ix_attendances_member_id", table_name="attendances")
    if _index_exists("attendances", "ix_attendances_meeting_id"):
        op.drop_index("ix_attendances_meeting_id", table_name="attendances")
    if _table_exists("attendances"):
        op.drop_table("attendances")

    if _index_exists("competition_results", "ix_competition_results_member_id"):
        op.drop_index("ix_competition_results_member_id", table_name="competition_results")
    if _index_exists("competition_results", "ix_competition_results_competition_id"):
        op.drop_index("ix_competition_results_competition_id", table_name="competition_results")
    if _table_exists("competition_results"):
        op.drop_table("competition_results")

    if _index_exists("meetings", "ix_meetings_meeting_type"):
        op.drop_index("ix_meetings_meeting_type", table_name="meetings")
    if _index_exists("meetings", "ix_meetings_title"):
        op.drop_index("ix_meetings_title", table_name="meetings")
    if _table_exists("meetings"):
        op.drop_table("meetings")

    if _index_exists("competitions", "ix_competitions_title"):
        op.drop_index("ix_competitions_title", table_name="competitions")
    if _table_exists("competitions"):
        op.drop_table("competitions")
