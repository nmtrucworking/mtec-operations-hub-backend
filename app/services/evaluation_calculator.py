import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.evaluation_constants import (
    CALCULATION_VERSION,
    COMPONENT_I,
    COMPONENT_II,
    COMPONENT_III_A,
    COMPONENT_III_B,
    COMPONENT_MAX_SCORES,
    CYCLE_MUTABLE_STATUSES,
    MEMBER_EVALUATION_STATUS_COMPUTED,
    TOTAL_MAX_SCORE,
    WEIGHT_TOLERANCE,
)
from app.models import (
    DisciplineCase,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationScoreEvent,
    Member,
    MemberCycleRole,
    MemberEvaluation,
    MemberEvaluationBreakdown,
    User,
)
from app.services.evaluation_classification import ClassificationPolicyService
from app.services.evaluation_errors import (
    EvaluationCycleLockedError,
    EvaluationMissingCriteriaError,
    EvaluationNotFoundError,
    EvaluationWeightError,
)
from app.services.evaluation_evidence import EvidenceValidationService


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(float(value), low), high)


class EvaluationCalculatorService:
    def __init__(self, db: Session):
        self.db = db
        self.evidence_service = EvidenceValidationService(db)
        self.classification_service = ClassificationPolicyService(db)

    def compute_cycle(
        self,
        cycle_id: str,
        *,
        actor_user_id: str | None = None,
        strict: bool = True,
        evidence_mode: str = "draft",
    ) -> dict:
        cycle = self._get_cycle(cycle_id)
        self._ensure_cycle_is_writable(cycle)
        member_ids = self._load_cycle_member_ids(cycle_id)

        computed = 0
        errors: list[dict] = []

        for member_id in member_ids:
            if strict:
                self.compute_member(
                    cycle_id,
                    member_id,
                    actor_user_id=actor_user_id,
                    strict=strict,
                    evidence_mode=evidence_mode,
                )
                computed += 1
                continue

            try:
                with self.db.begin_nested():
                    self.compute_member(
                        cycle_id,
                        member_id,
                        actor_user_id=actor_user_id,
                        strict=False,
                        evidence_mode=evidence_mode,
                    )
                computed += 1
            except Exception as exc:  # noqa: BLE001 - returned as batch summary
                errors.append(
                    {
                        "memberId": member_id,
                        "code": getattr(exc, "code", "EVALUATION_COMPUTE_ERROR"),
                        "message": str(exc),
                    }
                )

        actor = self.db.get(User, actor_user_id) if actor_user_id else None
        create_audit_log(
            db=self.db,
            action="COMPUTE_CYCLE_EVALUATION",
            resource_type="evaluation_cycle",
            resource_id=cycle_id,
            actor=actor,
            after_snapshot={
                "computedMembers": computed,
                "skippedMembers": len(errors),
                "calculationVersion": CALCULATION_VERSION,
            },
        )
        self.db.flush()

        return {
            "cycleId": cycle_id,
            "computedMembers": computed,
            "skippedMembers": len(errors),
            "errors": errors,
            "calculationVersion": CALCULATION_VERSION,
        }

    def compute_member(
        self,
        cycle_id: str,
        member_id: str,
        *,
        actor_user_id: str | None = None,
        strict: bool = True,
        evidence_mode: str = "draft",
    ) -> dict:
        cycle = self._get_cycle(cycle_id)
        self._ensure_cycle_is_writable(cycle)
        result = self._calculate_member(
            cycle=cycle,
            member_id=member_id,
            strict=strict,
            evidence_mode=evidence_mode,
        )

        member_evaluation = self._upsert_member_evaluation(result)
        self._replace_breakdowns(member_evaluation.id, result)

        actor = self.db.get(User, actor_user_id) if actor_user_id else None
        create_audit_log(
            db=self.db,
            action="COMPUTE_MEMBER_EVALUATION",
            resource_type="member_evaluation",
            resource_id=member_evaluation.id,
            actor=actor,
            after_snapshot={
                "cycleId": cycle_id,
                "memberId": member_id,
                "totalScore": result["totalScore"],
                "finalClassification": result["finalClassification"],
            },
        )
        self.db.flush()

        return {**result, "memberEvaluationId": member_evaluation.id}

    def preview_member(
        self,
        cycle_id: str,
        member_id: str,
        *,
        strict: bool = False,
        evidence_mode: str = "draft",
    ) -> dict:
        cycle = self._get_cycle(cycle_id)
        return self._calculate_member(
            cycle=cycle,
            member_id=member_id,
            strict=strict,
            evidence_mode=evidence_mode,
        )

    def preview_cycle(
        self,
        cycle_id: str,
        *,
        strict: bool = False,
        evidence_mode: str = "draft",
    ) -> dict:
        cycle = self._get_cycle(cycle_id)
        member_ids = self._load_cycle_member_ids(cycle_id)

        items: list[dict] = []
        errors: list[dict] = []

        for member_id in member_ids:
            try:
                result = self._calculate_member(
                    cycle=cycle,
                    member_id=member_id,
                    strict=strict,
                    evidence_mode=evidence_mode,
                )
                items.append(result)
            except Exception as exc:  # noqa: BLE001 - surfaced in preview summary
                errors.append(
                    {
                        "memberId": member_id,
                        "code": getattr(exc, "code", "EVALUATION_PREVIEW_ERROR"),
                        "message": str(exc),
                    }
                )
                if strict:
                    raise

        total_members = len(items)
        average_score = (
            round(sum(item["totalScore"] for item in items) / total_members, 2)
            if total_members > 0
            else 0.0
        )

        classification_distribution: dict[str, int] = {}
        for item in items:
            key = item.get("finalClassification") or "UNCLASSIFIED"
            classification_distribution[key] = (
                classification_distribution.get(key, 0) + 1
            )

        return {
            "cycleId": cycle_id,
            "totalMembers": total_members,
            "averageScore": average_score,
            "classificationDistribution": classification_distribution,
            "items": items,
            "errors": errors,
            "isTemporary": True,
            "persisted": False,
            "calculationVersion": CALCULATION_VERSION,
        }

    def get_cycle_member_ids(self, cycle_id: str) -> list[str]:
        return self._load_cycle_member_ids(cycle_id)

    def _calculate_member(
        self,
        *,
        cycle: EvaluationCycle,
        member_id: str,
        strict: bool,
        evidence_mode: str,
    ) -> dict:
        member = self._get_member(member_id)
        criteria = self._load_active_criteria(cycle)
        events = self._load_valid_events(cycle.id, member_id)
        evidence_count_by_event_id = self.evidence_service.count_evidence_for_events(
            (event.id for event in events if event.id), mode=evidence_mode
        )
        valid_events, warnings = self._filter_events_by_evidence(
            events,
            criteria,
            strict=strict,
            evidence_mode=evidence_mode,
            evidence_count_by_event_id=evidence_count_by_event_id,
        )
        roles = self._load_roles_or_fallback(cycle.id, member)

        breakdowns = self._calculate_breakdowns(
            criteria,
            valid_events,
            evidence_count_by_event_id=evidence_count_by_event_id,
        )
        component_scores = self._calculate_component_scores(breakdowns, roles)
        total_score = _clamp(sum(component_scores.values()), 0.0, TOTAL_MAX_SCORE)
        attendance_rate = self._extract_attendance_rate(valid_events)
        blockers = self.classification_service.collect_blockers(
            cycle_id=cycle.id,
            member_id=member_id,
            attendance_rate=attendance_rate,
        )
        preliminary = self.classification_service.classify_preliminary(total_score)
        final = self.classification_service.apply_blockers(preliminary, blockers)

        return {
            "cycleId": cycle.id,
            "memberId": member_id,
            "componentScores": {
                COMPONENT_I: component_scores[COMPONENT_I],
                COMPONENT_II: component_scores[COMPONENT_II],
                COMPONENT_III_A: component_scores[COMPONENT_III_A],
                COMPONENT_III_B: component_scores[COMPONENT_III_B],
            },
            "totalScore": total_score,
            "preliminaryClassification": preliminary,
            "finalClassification": final,
            "attendanceRate": attendance_rate,
            "blockers": blockers,
            "warnings": warnings,
            "breakdowns": breakdowns,
            "calculationVersion": CALCULATION_VERSION,
        }

    def _get_cycle(self, cycle_id: str) -> EvaluationCycle:
        cycle = self.db.get(EvaluationCycle, cycle_id)
        if not cycle:
            raise EvaluationNotFoundError(f"Evaluation cycle not found: {cycle_id}")
        return cycle

    def _get_member(self, member_id: str) -> Member:
        member = self.db.get(Member, member_id)
        if not member:
            raise EvaluationNotFoundError(f"Member not found: {member_id}")
        return member

    def _ensure_cycle_is_writable(self, cycle: EvaluationCycle) -> None:
        if cycle.status not in CYCLE_MUTABLE_STATUSES:
            raise EvaluationCycleLockedError(
                f"Evaluation cycle is not writable in status {cycle.status}: {cycle.id}"
            )

    def _load_active_criteria(self, cycle: EvaluationCycle) -> list[EvaluationCriterion]:
        criteria = self.db.scalars(
            select(EvaluationCriterion)
            .where(
                EvaluationCriterion.is_active.is_(True),
                or_(
                    EvaluationCriterion.effective_from.is_(None),
                    EvaluationCriterion.effective_from <= cycle.end_date,
                ),
                or_(
                    EvaluationCriterion.effective_to.is_(None),
                    EvaluationCriterion.effective_to >= cycle.start_date,
                ),
            )
            .order_by(EvaluationCriterion.sort_order, EvaluationCriterion.code)
        ).all()

        if not criteria:
            raise EvaluationMissingCriteriaError(
                f"No active evaluation criteria found for cycle {cycle.id}"
            )

        return criteria

    def _load_valid_events(
        self, cycle_id: str, member_id: str
    ) -> list[EvaluationScoreEvent]:
        return self.db.scalars(
            select(EvaluationScoreEvent).where(
                EvaluationScoreEvent.cycle_id == cycle_id,
                EvaluationScoreEvent.member_id == member_id,
                EvaluationScoreEvent.is_void.is_(False),
            )
        ).all()

    def _filter_events_by_evidence(
        self,
        events: list[EvaluationScoreEvent],
        criteria: list[EvaluationCriterion],
        *,
        strict: bool,
        evidence_mode: str,
        evidence_count_by_event_id: dict[str, int] | None = None,
    ) -> tuple[list[EvaluationScoreEvent], list[dict]]:
        criterion_by_id = {criterion.id: criterion for criterion in criteria}
        events_in_active_criteria = [
            event for event in events if event.criterion_id in criterion_by_id
        ]
        warnings = self.evidence_service.validate_score_events(
            events_in_active_criteria,
            strict=strict,
            mode=evidence_mode,
            evidence_count_by_event_id=evidence_count_by_event_id,
        )
        missing_event_ids = {warning["scoreEventId"] for warning in warnings}
        valid_events = [
            event for event in events_in_active_criteria if event.id not in missing_event_ids
        ]
        return valid_events, warnings

    def _load_roles_or_fallback(self, cycle_id: str, member: Member) -> list[dict]:
        roles = self.db.scalars(
            select(MemberCycleRole).where(
                MemberCycleRole.cycle_id == cycle_id,
                MemberCycleRole.member_id == member.id,
            )
        ).all()

        if not roles:
            if member.ban:
                return [
                    {
                        "unitCode": member.ban,
                        "participationWeight": 1.0,
                        "isPrimary": True,
                        "source": "member.ban",
                    }
                ]
            return []

        total_weight = sum(role.participation_weight or 0.0 for role in roles)
        if abs(total_weight - 1.0) > WEIGHT_TOLERANCE:
            raise EvaluationWeightError(
                f"Member {member.id} role weights must sum to 1.0, got {total_weight}"
            )

        primary_count = sum(1 for role in roles if role.is_primary)
        if primary_count > 1:
            raise EvaluationWeightError(f"Member {member.id} has multiple primary roles")

        return [
            {
                "unitCode": role.unit_code,
                "participationWeight": role.participation_weight or 0.0,
                "isPrimary": role.is_primary,
                "source": "member_cycle_roles",
            }
            for role in roles
        ]

    def _calculate_breakdowns(
        self,
        criteria: list[EvaluationCriterion],
        events: list[EvaluationScoreEvent],
        *,
        evidence_count_by_event_id: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        events_by_criterion_id: dict[str, list[EvaluationScoreEvent]] = {}
        for event in events:
            events_by_criterion_id.setdefault(event.criterion_id, []).append(event)

        if evidence_count_by_event_id is None:
            evidence_count_by_event_id = self.evidence_service.count_evidence_for_events(
                (event.id for event in events if event.id)
            )

        breakdowns: list[dict[str, Any]] = []
        for criterion in criteria:
            related_events = events_by_criterion_id.get(criterion.id, [])
            event_total = sum(event.score_delta for event in related_events)
            if (criterion.score_method or "").upper() == "DEDUCTIVE":
                raw_score = criterion.max_score + event_total
            else:
                raw_score = event_total
            final_score = _clamp(raw_score, 0.0, criterion.max_score)
            evidence_count = sum(
                evidence_count_by_event_id.get(event.id, 0)
                for event in related_events
                if event.id
            )
            breakdowns.append(
                {
                    "criterionId": criterion.id,
                    "criterionCode": criterion.code,
                    "component": criterion.component,
                    "unitCode": criterion.unit_code,
                    "rawScore": raw_score,
                    "finalScore": final_score,
                    "maxScoreSnapshot": criterion.max_score,
                    "capApplied": raw_score != final_score,
                    "evidenceCount": evidence_count,
                    "calculationNote": None,
                }
            )

        return breakdowns

    def _calculate_component_scores(
        self, breakdowns: list[dict[str, Any]], roles: list[dict]
    ) -> dict[str, float]:
        component_i = _clamp(
            sum(item["finalScore"] for item in breakdowns if item["component"] == COMPONENT_I),
            0.0,
            COMPONENT_MAX_SCORES[COMPONENT_I],
        )
        component_ii = _clamp(
            sum(item["finalScore"] for item in breakdowns if item["component"] == COMPONENT_II),
            0.0,
            COMPONENT_MAX_SCORES[COMPONENT_II],
        )
        component_iii_a = _clamp(
            sum(
                item["finalScore"]
                for item in breakdowns
                if item["component"] == COMPONENT_III_A
            ),
            0.0,
            COMPONENT_MAX_SCORES[COMPONENT_III_A],
        )
        component_iii_b = self._calculate_weighted_iii_b(breakdowns, roles)

        return {
            COMPONENT_I: component_i,
            COMPONENT_II: component_ii,
            COMPONENT_III_A: component_iii_a,
            COMPONENT_III_B: component_iii_b,
        }

    def _calculate_weighted_iii_b(
        self, breakdowns: list[dict[str, Any]], roles: list[dict]
    ) -> float:
        if not roles:
            return 0.0

        score = 0.0
        for role in roles:
            unit_code = role["unitCode"]
            unit_score = sum(
                item["finalScore"]
                for item in breakdowns
                if item["component"] == COMPONENT_III_B and item["unitCode"] == unit_code
            )
            capped_unit_score = _clamp(
                unit_score, 0.0, COMPONENT_MAX_SCORES[COMPONENT_III_B]
            )
            score += capped_unit_score * role["participationWeight"]

        return _clamp(score, 0.0, COMPONENT_MAX_SCORES[COMPONENT_III_B])

    def _extract_attendance_rate(
        self, events: list[EvaluationScoreEvent]
    ) -> float | None:
        attendance_events = [
            event
            for event in events
            if event.criterion_code == "I.1" and event.raw_value is not None
        ]
        if not attendance_events:
            return None
        return max(0.0, min(float(attendance_events[-1].raw_value), 1.0))

    def _upsert_member_evaluation(self, result: dict) -> MemberEvaluation:
        member_evaluation = self.db.scalar(
            select(MemberEvaluation).where(
                MemberEvaluation.cycle_id == result["cycleId"],
                MemberEvaluation.member_id == result["memberId"],
            )
        )
        if member_evaluation is None:
            member_evaluation = MemberEvaluation(
                cycle_id=result["cycleId"],
                member_id=result["memberId"],
            )
            self.db.add(member_evaluation)
            self.db.flush()

        component_scores = result["componentScores"]
        member_evaluation.component_i_score = component_scores[COMPONENT_I]
        member_evaluation.component_ii_score = component_scores[COMPONENT_II]
        member_evaluation.component_iii_a_score = component_scores[COMPONENT_III_A]
        member_evaluation.component_iii_b_score = component_scores[COMPONENT_III_B]
        member_evaluation.total_score = result["totalScore"]
        member_evaluation.preliminary_classification = result[
            "preliminaryClassification"
        ]
        member_evaluation.final_classification = result["finalClassification"]
        member_evaluation.status = MEMBER_EVALUATION_STATUS_COMPUTED
        member_evaluation.attendance_rate = result["attendanceRate"]
        member_evaluation.blockers_json = json.dumps(
            result["blockers"], ensure_ascii=True, default=str
        )
        member_evaluation.calculation_version = CALCULATION_VERSION
        member_evaluation.computed_at = datetime.now(UTC)

        return member_evaluation

    def _replace_breakdowns(
        self, member_evaluation_id: str, result: dict
    ) -> None:
        self.db.execute(
            delete(MemberEvaluationBreakdown).where(
                MemberEvaluationBreakdown.member_evaluation_id == member_evaluation_id
            )
        )

        for item in result["breakdowns"]:
            self.db.add(
                MemberEvaluationBreakdown(
                    member_evaluation_id=member_evaluation_id,
                    cycle_id=result["cycleId"],
                    member_id=result["memberId"],
                    criterion_id=item["criterionId"],
                    criterion_code=item["criterionCode"],
                    component=item["component"],
                    unit_code=item["unitCode"],
                    raw_score=item["rawScore"],
                    final_score=item["finalScore"],
                    max_score_snapshot=item["maxScoreSnapshot"],
                    cap_applied=item["capApplied"],
                    evidence_count=item["evidenceCount"],
                    calculation_note=item["calculationNote"],
                )
            )

    def _load_cycle_member_ids(self, cycle_id: str) -> list[str]:
        member_ids: set[str] = set()
        member_ids.update(
            self.db.scalars(
                select(Member.id).where(Member.status == "Active")
            ).all()
        )
        member_ids.update(
            self.db.scalars(
                select(EvaluationScoreEvent.member_id).where(
                    EvaluationScoreEvent.cycle_id == cycle_id,
                    EvaluationScoreEvent.is_void.is_(False),
                )
            ).all()
        )
        member_ids.update(
            self.db.scalars(
                select(MemberCycleRole.member_id).where(MemberCycleRole.cycle_id == cycle_id)
            ).all()
        )
        member_ids.update(
            self.db.scalars(
                select(DisciplineCase.member_id).where(
                    DisciplineCase.cycle_id == cycle_id,
                    DisciplineCase.status != "CANCELLED",
                )
            ).all()
        )
        return sorted(member_ids)
