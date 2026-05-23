"""add unique constraint on evaluation_evidence.score_event_id

Revision ID: ea5b2c1f4a6f
Revises: d2a1f7e9b001
Create Date: 2026-05-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ea5b2c1f4a6f"
down_revision: str | None = "d2a1f7e9b001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _uq_exists(table_name: str, uq_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # search unique constraints
    uqs = inspector.get_unique_constraints(table_name)
    return any(uq.get("name") == uq_name for uq in uqs)


def upgrade() -> None:
    if _table_exists("evaluation_evidence") and not _uq_exists(
        "evaluation_evidence", "uq_evaluation_evidence_score_event"
    ):
        bind = op.get_bind()
        
        # Deduplicate existing evidence for the same score_event_id
        dup_query = """
        SELECT score_event_id
        FROM evaluation_evidence
        WHERE score_event_id IS NOT NULL
        GROUP BY score_event_id
        HAVING COUNT(*) > 1
        """
        res = bind.execute(sa.text(dup_query)).fetchall()
        if res and len(res) > 0:
            dup_ids = [row[0] for row in res]
            for event_id in dup_ids:
                # Get all evidence ids for this score_event_id
                evidence_query = sa.text("""
                    SELECT id FROM evaluation_evidence 
                    WHERE score_event_id = :event_id 
                    ORDER BY created_at DESC
                """)
                evidence_rows = bind.execute(evidence_query, {"event_id": event_id}).fetchall()
                if len(evidence_rows) > 1:
                    # Keep the first one, delete the rest
                    ids_to_delete = [row[0] for row in evidence_rows[1:]]
                    for del_id in ids_to_delete:
                        bind.execute(sa.text("DELETE FROM evaluation_evidence WHERE id = :id"), {"id": del_id})
                        
        # add unique constraint on score_event_id to prevent duplicates
        # SQLite does not support ALTER CONSTRAINT directly; use batch_alter_table for compatibility
        if bind.dialect.name == 'sqlite':
            with op.batch_alter_table('evaluation_evidence') as batch_op:
                batch_op.create_unique_constraint(
                    "uq_evaluation_evidence_score_event", ["score_event_id"]
                )
        else:
            op.create_unique_constraint(
                "uq_evaluation_evidence_score_event", "evaluation_evidence", ["score_event_id"]
            )


def downgrade() -> None:
    if _table_exists("evaluation_evidence") and _uq_exists(
        "evaluation_evidence", "uq_evaluation_evidence_score_event"
    ):
        bind = op.get_bind()
        if bind.dialect.name == 'sqlite':
            with op.batch_alter_table('evaluation_evidence') as batch_op:
                batch_op.drop_constraint("uq_evaluation_evidence_score_event")
        else:
            op.drop_constraint(
                "uq_evaluation_evidence_score_event", "evaluation_evidence", type_="unique"
            )
