"""add evaluation evidence applied events

Revision ID: b7c8d9e0f1a2
Revises: ea5b2c1f4a6f
Create Date: 2026-06-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "ea5b2c1f4a6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_evidence_applied_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("score_event_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evaluation_evidence.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["score_event_id"],
            ["evaluation_score_events.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_id",
            "score_event_id",
            name="uq_evaluation_evidence_applied_events_evidence_event",
        ),
    )
    op.create_index(
        "ix_evaluation_evidence_applied_events_evidence_id",
        "evaluation_evidence_applied_events",
        ["evidence_id"],
    )
    op.create_index(
        "ix_evaluation_evidence_applied_events_score_event_id",
        "evaluation_evidence_applied_events",
        ["score_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_evidence_applied_events_score_event_id",
        table_name="evaluation_evidence_applied_events",
    )
    op.drop_index(
        "ix_evaluation_evidence_applied_events_evidence_id",
        table_name="evaluation_evidence_applied_events",
    )
    op.drop_table("evaluation_evidence_applied_events")
