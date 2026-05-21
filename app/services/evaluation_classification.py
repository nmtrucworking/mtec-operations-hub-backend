from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.evaluation_constants import (
    BLOCKER_ATTENDANCE_UNDER_80,
    BLOCKER_CLASSIFICATION_CAPS,
    CLASSIFICATION_EXCELLENT,
    CLASSIFICATION_FAILED,
    CLASSIFICATION_GOOD,
    CLASSIFICATION_NEEDS_IMPROVEMENT,
    CLASSIFICATION_PASSED,
    CLASSIFICATION_RANK,
)
from app.models import DisciplineCase


class ClassificationPolicyService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def classify_preliminary(self, total_score: float) -> str:
        score = max(float(total_score), 0.0)
        if score >= 90.0:
            return CLASSIFICATION_EXCELLENT
        if score >= 80.0:
            return CLASSIFICATION_GOOD
        if score >= 65.0:
            return CLASSIFICATION_PASSED
        if score >= 50.0:
            return CLASSIFICATION_NEEDS_IMPROVEMENT
        return CLASSIFICATION_FAILED

    def apply_blockers(self, preliminary: str, blockers: list[dict]) -> str:
        final = preliminary
        final_rank = CLASSIFICATION_RANK[final]

        for blocker in blockers:
            cap = blocker.get("cap") or BLOCKER_CLASSIFICATION_CAPS.get(blocker.get("code"))
            if not cap:
                continue
            cap_rank = CLASSIFICATION_RANK[cap]
            if cap_rank < final_rank:
                final = cap
                final_rank = cap_rank

        return final

    def collect_blockers(
        self, *, cycle_id: str, member_id: str, attendance_rate: float | None
    ) -> list[dict]:
        blockers: list[dict] = []

        if attendance_rate is not None and attendance_rate < 0.8:
            blockers.append(
                {
                    "code": BLOCKER_ATTENDANCE_UNDER_80,
                    "cap": BLOCKER_CLASSIFICATION_CAPS[BLOCKER_ATTENDANCE_UNDER_80],
                    "source": "attendance_rate",
                    "value": attendance_rate,
                }
            )

        if self.db is None:
            return blockers

        cases = self.db.scalars(
            select(DisciplineCase).where(
                DisciplineCase.cycle_id == cycle_id,
                DisciplineCase.member_id == member_id,
                DisciplineCase.status != "CANCELLED",
                DisciplineCase.blocker_code.is_not(None),
            )
        ).all()

        for case in cases:
            if case.blocker_code not in BLOCKER_CLASSIFICATION_CAPS:
                continue
            blockers.append(
                {
                    "code": case.blocker_code,
                    "cap": BLOCKER_CLASSIFICATION_CAPS[case.blocker_code],
                    "source": "discipline_case",
                    "caseId": case.id,
                    "severity": case.severity,
                    "title": case.title,
                }
            )

        return blockers

    def classify(
        self, *, total_score: float, blockers: list[dict]
    ) -> dict[str, str | list[dict]]:
        preliminary = self.classify_preliminary(total_score)
        final = self.apply_blockers(preliminary, blockers)
        return {
            "preliminaryClassification": preliminary,
            "finalClassification": final,
            "blockers": blockers,
        }
