"""add evaluation core tables

Revision ID: d2a1f7e9b001
Revises: 9dcf6450482f
Create Date: 2026-05-21 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2a1f7e9b001"
down_revision: str | None = "9dcf6450482f"
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


def _create_index(
    table_name: str, index_name: str, columns: list[str], *, unique: bool = False
) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index(table_name: str, index_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _table_exists("evaluation_cycles"):
        op.create_table(
            "evaluation_cycles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("type", sa.String(length=30), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("locked_at", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_evaluation_cycles_code"),
        )
    _create_index("evaluation_cycles", "ix_evaluation_cycles_status", ["status"])
    _create_index("evaluation_cycles", "ix_evaluation_cycles_type", ["type"])
    _create_index("evaluation_cycles", "ix_evaluation_cycles_start_date", ["start_date"])
    _create_index("evaluation_cycles", "ix_evaluation_cycles_end_date", ["end_date"])

    if not _table_exists("evaluation_criteria"):
        op.create_table(
            "evaluation_criteria",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("component", sa.String(length=20), nullable=False),
            sa.Column("unit_scope", sa.String(length=30), nullable=False),
            sa.Column("unit_code", sa.String(length=30), nullable=True),
            sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("score_method", sa.String(length=30), nullable=False),
            sa.Column("requires_evidence", sa.Boolean(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=True),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "code",
                "unit_code",
                "effective_from",
                name="uq_evaluation_criteria_code_unit_effective",
            ),
        )
    _create_index("evaluation_criteria", "ix_evaluation_criteria_component", ["component"])
    _create_index("evaluation_criteria", "ix_evaluation_criteria_unit_code", ["unit_code"])
    _create_index("evaluation_criteria", "ix_evaluation_criteria_is_active", ["is_active"])

    if not _table_exists("member_cycle_roles"):
        op.create_table(
            "member_cycle_roles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("cycle_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("unit_code", sa.String(length=30), nullable=False),
            sa.Column("role_type", sa.String(length=30), nullable=False),
            sa.Column("role_title", sa.String(length=120), nullable=True),
            sa.Column("participation_weight", sa.Float(), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False),
            sa.Column("assigned_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_id"], ["evaluation_cycles.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "cycle_id",
                "member_id",
                "unit_code",
                name="uq_member_cycle_roles_cycle_member_unit",
            ),
        )
    _create_index("member_cycle_roles", "ix_member_cycle_roles_cycle_id", ["cycle_id"])
    _create_index("member_cycle_roles", "ix_member_cycle_roles_member_id", ["member_id"])
    _create_index("member_cycle_roles", "ix_member_cycle_roles_unit_code", ["unit_code"])
    _create_index("member_cycle_roles", "ix_member_cycle_roles_role_type", ["role_type"])
    _create_index("member_cycle_roles", "ix_member_cycle_roles_is_primary", ["is_primary"])

    if not _table_exists("evaluation_score_events"):
        op.create_table(
            "evaluation_score_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("cycle_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("criterion_id", sa.String(length=36), nullable=False),
            sa.Column("criterion_code", sa.String(length=50), nullable=False),
            sa.Column("component", sa.String(length=20), nullable=False),
            sa.Column("unit_code", sa.String(length=30), nullable=True),
            sa.Column("event_type", sa.String(length=30), nullable=False),
            sa.Column("source_type", sa.String(length=50), nullable=True),
            sa.Column("source_id", sa.String(length=80), nullable=True),
            sa.Column("raw_value", sa.Float(), nullable=True),
            sa.Column("score_delta", sa.Float(), nullable=False),
            sa.Column("max_score_snapshot", sa.Float(), nullable=True),
            sa.Column("weight", sa.Float(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("recorded_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("recorded_at", sa.DateTime(), nullable=False),
            sa.Column("is_void", sa.Boolean(), nullable=False),
            sa.Column("void_reason", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_id"], ["evaluation_cycles.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.ForeignKeyConstraint(["criterion_id"], ["evaluation_criteria.id"]),
            sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "cycle_id",
                "member_id",
                "criterion_code",
                "source_type",
                "source_id",
                "event_type",
                name="uq_evaluation_score_events_source_dedupe",
            ),
        )
    _create_index("evaluation_score_events", "ix_evaluation_score_events_cycle_id", ["cycle_id"])
    _create_index("evaluation_score_events", "ix_evaluation_score_events_member_id", ["member_id"])
    _create_index(
        "evaluation_score_events", "ix_evaluation_score_events_criterion_id", ["criterion_id"]
    )
    _create_index(
        "evaluation_score_events",
        "ix_evaluation_score_events_criterion_code",
        ["criterion_code"],
    )
    _create_index("evaluation_score_events", "ix_evaluation_score_events_component", ["component"])
    _create_index("evaluation_score_events", "ix_evaluation_score_events_unit_code", ["unit_code"])
    _create_index("evaluation_score_events", "ix_evaluation_score_events_event_type", ["event_type"])
    _create_index("evaluation_score_events", "ix_evaluation_score_events_source_type", ["source_type"])
    _create_index("evaluation_score_events", "ix_evaluation_score_events_source_id", ["source_id"])
    _create_index("evaluation_score_events", "ix_evaluation_score_events_is_void", ["is_void"])

    if not _table_exists("evaluation_evidence"):
        op.create_table(
            "evaluation_evidence",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("cycle_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("criterion_id", sa.String(length=36), nullable=True),
            sa.Column("score_event_id", sa.String(length=36), nullable=True),
            sa.Column("evidence_type", sa.String(length=30), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=True),
            sa.Column("file_path", sa.String(length=500), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("captured_at", sa.DateTime(), nullable=True),
            sa.Column("submitted_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("verified_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_id"], ["evaluation_cycles.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.ForeignKeyConstraint(["criterion_id"], ["evaluation_criteria.id"]),
            sa.ForeignKeyConstraint(["score_event_id"], ["evaluation_score_events.id"]),
            sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("evaluation_evidence", "ix_evaluation_evidence_cycle_id", ["cycle_id"])
    _create_index("evaluation_evidence", "ix_evaluation_evidence_member_id", ["member_id"])
    _create_index("evaluation_evidence", "ix_evaluation_evidence_criterion_id", ["criterion_id"])
    _create_index(
        "evaluation_evidence", "ix_evaluation_evidence_score_event_id", ["score_event_id"]
    )
    _create_index("evaluation_evidence", "ix_evaluation_evidence_evidence_type", ["evidence_type"])
    _create_index("evaluation_evidence", "ix_evaluation_evidence_status", ["status"])

    if not _table_exists("member_evaluations"):
        op.create_table(
            "member_evaluations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("cycle_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("component_i_score", sa.Float(), nullable=False),
            sa.Column("component_ii_score", sa.Float(), nullable=False),
            sa.Column("component_iii_a_score", sa.Float(), nullable=False),
            sa.Column("component_iii_b_score", sa.Float(), nullable=False),
            sa.Column("total_score", sa.Float(), nullable=False),
            sa.Column("preliminary_classification", sa.String(length=40), nullable=True),
            sa.Column("final_classification", sa.String(length=40), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("attendance_rate", sa.Float(), nullable=True),
            sa.Column("blockers_json", sa.Text(), nullable=True),
            sa.Column("calculation_version", sa.String(length=50), nullable=True),
            sa.Column("computed_at", sa.DateTime(), nullable=True),
            sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_id"], ["evaluation_cycles.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cycle_id", "member_id", name="uq_member_evaluations_cycle_member"),
        )
    _create_index("member_evaluations", "ix_member_evaluations_cycle_id", ["cycle_id"])
    _create_index("member_evaluations", "ix_member_evaluations_member_id", ["member_id"])
    _create_index("member_evaluations", "ix_member_evaluations_status", ["status"])
    _create_index(
        "member_evaluations",
        "ix_member_evaluations_final_classification",
        ["final_classification"],
    )
    _create_index("member_evaluations", "ix_member_evaluations_total_score", ["total_score"])

    if not _table_exists("member_evaluation_breakdowns"):
        op.create_table(
            "member_evaluation_breakdowns",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("member_evaluation_id", sa.String(length=36), nullable=False),
            sa.Column("cycle_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("criterion_id", sa.String(length=36), nullable=False),
            sa.Column("criterion_code", sa.String(length=50), nullable=False),
            sa.Column("component", sa.String(length=20), nullable=False),
            sa.Column("unit_code", sa.String(length=30), nullable=True),
            sa.Column("raw_score", sa.Float(), nullable=False),
            sa.Column("final_score", sa.Float(), nullable=False),
            sa.Column("max_score_snapshot", sa.Float(), nullable=False),
            sa.Column("cap_applied", sa.Boolean(), nullable=False),
            sa.Column("evidence_count", sa.Integer(), nullable=False),
            sa.Column("calculation_note", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["member_evaluation_id"], ["member_evaluations.id"]),
            sa.ForeignKeyConstraint(["cycle_id"], ["evaluation_cycles.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.ForeignKeyConstraint(["criterion_id"], ["evaluation_criteria.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "member_evaluation_id",
                "criterion_code",
                "unit_code",
                name="uq_member_evaluation_breakdowns_eval_criterion_unit",
            ),
        )
    _create_index(
        "member_evaluation_breakdowns",
        "ix_member_evaluation_breakdowns_cycle_id",
        ["cycle_id"],
    )
    _create_index(
        "member_evaluation_breakdowns",
        "ix_member_evaluation_breakdowns_member_id",
        ["member_id"],
    )
    _create_index(
        "member_evaluation_breakdowns",
        "ix_member_evaluation_breakdowns_criterion_id",
        ["criterion_id"],
    )
    _create_index(
        "member_evaluation_breakdowns",
        "ix_member_evaluation_breakdowns_criterion_code",
        ["criterion_code"],
    )
    _create_index(
        "member_evaluation_breakdowns",
        "ix_member_evaluation_breakdowns_component",
        ["component"],
    )
    _create_index(
        "member_evaluation_breakdowns",
        "ix_member_evaluation_breakdowns_unit_code",
        ["unit_code"],
    )

    if not _table_exists("evaluation_appeals"):
        op.create_table(
            "evaluation_appeals",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("cycle_id", sa.String(length=36), nullable=False),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("member_evaluation_id", sa.String(length=36), nullable=True),
            sa.Column("criterion_id", sa.String(length=36), nullable=True),
            sa.Column("criterion_code", sa.String(length=50), nullable=True),
            sa.Column("appeal_type", sa.String(length=50), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("requested_score", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_id"], ["evaluation_cycles.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.ForeignKeyConstraint(["member_evaluation_id"], ["member_evaluations.id"]),
            sa.ForeignKeyConstraint(["criterion_id"], ["evaluation_criteria.id"]),
            sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("evaluation_appeals", "ix_evaluation_appeals_cycle_id", ["cycle_id"])
    _create_index("evaluation_appeals", "ix_evaluation_appeals_member_id", ["member_id"])
    _create_index(
        "evaluation_appeals", "ix_evaluation_appeals_member_evaluation_id", ["member_evaluation_id"]
    )
    _create_index("evaluation_appeals", "ix_evaluation_appeals_criterion_id", ["criterion_id"])
    _create_index("evaluation_appeals", "ix_evaluation_appeals_status", ["status"])
    _create_index("evaluation_appeals", "ix_evaluation_appeals_appeal_type", ["appeal_type"])

    if not _table_exists("discipline_cases"):
        op.create_table(
            "discipline_cases",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("cycle_id", sa.String(length=36), nullable=True),
            sa.Column("member_id", sa.String(length=36), nullable=False),
            sa.Column("case_code", sa.String(length=80), nullable=True),
            sa.Column("case_type", sa.String(length=50), nullable=False),
            sa.Column("severity", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("blocker_code", sa.String(length=80), nullable=True),
            sa.Column("point_impact", sa.Float(), nullable=True),
            sa.Column("source_type", sa.String(length=50), nullable=True),
            sa.Column("source_id", sa.String(length=80), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_id"], ["evaluation_cycles.id"]),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("case_code", name="uq_discipline_cases_case_code"),
        )
    _create_index("discipline_cases", "ix_discipline_cases_cycle_id", ["cycle_id"])
    _create_index("discipline_cases", "ix_discipline_cases_member_id", ["member_id"])
    _create_index("discipline_cases", "ix_discipline_cases_case_type", ["case_type"])
    _create_index("discipline_cases", "ix_discipline_cases_severity", ["severity"])
    _create_index("discipline_cases", "ix_discipline_cases_status", ["status"])
    _create_index("discipline_cases", "ix_discipline_cases_blocker_code", ["blocker_code"])


def downgrade() -> None:
    _drop_index("discipline_cases", "ix_discipline_cases_blocker_code")
    _drop_index("discipline_cases", "ix_discipline_cases_status")
    _drop_index("discipline_cases", "ix_discipline_cases_severity")
    _drop_index("discipline_cases", "ix_discipline_cases_case_type")
    _drop_index("discipline_cases", "ix_discipline_cases_member_id")
    _drop_index("discipline_cases", "ix_discipline_cases_cycle_id")
    if _table_exists("discipline_cases"):
        op.drop_table("discipline_cases")

    _drop_index("evaluation_appeals", "ix_evaluation_appeals_appeal_type")
    _drop_index("evaluation_appeals", "ix_evaluation_appeals_status")
    _drop_index("evaluation_appeals", "ix_evaluation_appeals_criterion_id")
    _drop_index("evaluation_appeals", "ix_evaluation_appeals_member_evaluation_id")
    _drop_index("evaluation_appeals", "ix_evaluation_appeals_member_id")
    _drop_index("evaluation_appeals", "ix_evaluation_appeals_cycle_id")
    if _table_exists("evaluation_appeals"):
        op.drop_table("evaluation_appeals")

    _drop_index("member_evaluation_breakdowns", "ix_member_evaluation_breakdowns_unit_code")
    _drop_index("member_evaluation_breakdowns", "ix_member_evaluation_breakdowns_component")
    _drop_index("member_evaluation_breakdowns", "ix_member_evaluation_breakdowns_criterion_code")
    _drop_index("member_evaluation_breakdowns", "ix_member_evaluation_breakdowns_criterion_id")
    _drop_index("member_evaluation_breakdowns", "ix_member_evaluation_breakdowns_member_id")
    _drop_index("member_evaluation_breakdowns", "ix_member_evaluation_breakdowns_cycle_id")
    if _table_exists("member_evaluation_breakdowns"):
        op.drop_table("member_evaluation_breakdowns")

    _drop_index("member_evaluations", "ix_member_evaluations_total_score")
    _drop_index("member_evaluations", "ix_member_evaluations_final_classification")
    _drop_index("member_evaluations", "ix_member_evaluations_status")
    _drop_index("member_evaluations", "ix_member_evaluations_member_id")
    _drop_index("member_evaluations", "ix_member_evaluations_cycle_id")
    if _table_exists("member_evaluations"):
        op.drop_table("member_evaluations")

    _drop_index("evaluation_evidence", "ix_evaluation_evidence_status")
    _drop_index("evaluation_evidence", "ix_evaluation_evidence_evidence_type")
    _drop_index("evaluation_evidence", "ix_evaluation_evidence_score_event_id")
    _drop_index("evaluation_evidence", "ix_evaluation_evidence_criterion_id")
    _drop_index("evaluation_evidence", "ix_evaluation_evidence_member_id")
    _drop_index("evaluation_evidence", "ix_evaluation_evidence_cycle_id")
    if _table_exists("evaluation_evidence"):
        op.drop_table("evaluation_evidence")

    _drop_index("evaluation_score_events", "ix_evaluation_score_events_is_void")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_source_id")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_source_type")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_event_type")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_unit_code")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_component")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_criterion_code")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_criterion_id")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_member_id")
    _drop_index("evaluation_score_events", "ix_evaluation_score_events_cycle_id")
    if _table_exists("evaluation_score_events"):
        op.drop_table("evaluation_score_events")

    _drop_index("member_cycle_roles", "ix_member_cycle_roles_is_primary")
    _drop_index("member_cycle_roles", "ix_member_cycle_roles_role_type")
    _drop_index("member_cycle_roles", "ix_member_cycle_roles_unit_code")
    _drop_index("member_cycle_roles", "ix_member_cycle_roles_member_id")
    _drop_index("member_cycle_roles", "ix_member_cycle_roles_cycle_id")
    if _table_exists("member_cycle_roles"):
        op.drop_table("member_cycle_roles")

    _drop_index("evaluation_criteria", "ix_evaluation_criteria_is_active")
    _drop_index("evaluation_criteria", "ix_evaluation_criteria_unit_code")
    _drop_index("evaluation_criteria", "ix_evaluation_criteria_component")
    if _table_exists("evaluation_criteria"):
        op.drop_table("evaluation_criteria")

    _drop_index("evaluation_cycles", "ix_evaluation_cycles_end_date")
    _drop_index("evaluation_cycles", "ix_evaluation_cycles_start_date")
    _drop_index("evaluation_cycles", "ix_evaluation_cycles_type")
    _drop_index("evaluation_cycles", "ix_evaluation_cycles_status")
    if _table_exists("evaluation_cycles"):
        op.drop_table("evaluation_cycles")
