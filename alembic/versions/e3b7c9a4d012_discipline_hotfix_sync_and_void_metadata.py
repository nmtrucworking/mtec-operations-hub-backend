"""discipline hotfix sync and void metadata

Revision ID: e3b7c9a4d012
Revises: d2a1f7e9b001
Create Date: 2026-05-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3b7c9a4d012"
down_revision: str | None = "d2a1f7e9b001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    if not _column_exists("evaluation_score_events", "voided_at"):
        op.add_column(
            "evaluation_score_events",
            sa.Column("voided_at", sa.DateTime(), nullable=True),
        )
    if not _column_exists("evaluation_score_events", "voided_by_user_id"):
        op.add_column(
            "evaluation_score_events",
            sa.Column("voided_by_user_id", sa.String(length=36), nullable=True),
        )

    if not _table_exists("discipline_attendance_sync_logs"):
        op.create_table(
            "discipline_attendance_sync_logs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("meeting_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("discipline_record_id", sa.String(length=36), nullable=True),
            sa.Column("synced_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.ForeignKeyConstraint(["discipline_record_id"], ["discipline_records.id"]),
            sa.ForeignKeyConstraint(["synced_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "meeting_id",
                "member_id",
                name="uq_discipline_attendance_sync_logs_meeting_member",
            ),
        )
    if not _index_exists(
        "discipline_attendance_sync_logs",
        "ix_discipline_attendance_sync_logs_meeting_id",
    ):
        op.create_index(
            "ix_discipline_attendance_sync_logs_meeting_id",
            "discipline_attendance_sync_logs",
            ["meeting_id"],
        )
    if not _index_exists(
        "discipline_attendance_sync_logs",
        "ix_discipline_attendance_sync_logs_member_id",
    ):
        op.create_index(
            "ix_discipline_attendance_sync_logs_member_id",
            "discipline_attendance_sync_logs",
            ["member_id"],
        )

    op.execute(
        sa.text(
            """
            UPDATE discipline_records
            SET discipline_level = 'NONE'
            WHERE lower(discipline_level) IN ('', 'khong', 'không', 'none', 'n/a')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE discipline_records
            SET discipline_level = 'REMINDER'
            WHERE lower(discipline_level) IN ('nhac nho', 'nhắc nhở', 'reminder')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE discipline_records
            SET discipline_level = 'WARNING_1'
            WHERE lower(discipline_level) IN (
                'canh cao',
                'canh cao lan 1',
                'cảnh cáo',
                'cảnh cáo lần 1',
                'warning',
                'warning_1'
            )
            """
        )
    )


def downgrade() -> None:
    if _index_exists(
        "discipline_attendance_sync_logs",
        "ix_discipline_attendance_sync_logs_member_id",
    ):
        op.drop_index(
            "ix_discipline_attendance_sync_logs_member_id",
            table_name="discipline_attendance_sync_logs",
        )
    if _index_exists(
        "discipline_attendance_sync_logs",
        "ix_discipline_attendance_sync_logs_meeting_id",
    ):
        op.drop_index(
            "ix_discipline_attendance_sync_logs_meeting_id",
            table_name="discipline_attendance_sync_logs",
        )
    if _table_exists("discipline_attendance_sync_logs"):
        op.drop_table("discipline_attendance_sync_logs")
    if _column_exists("evaluation_score_events", "voided_by_user_id"):
        op.drop_column("evaluation_score_events", "voided_by_user_id")
    if _column_exists("evaluation_score_events", "voided_at"):
        op.drop_column("evaluation_score_events", "voided_at")
