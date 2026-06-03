from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.evaluation_constants import (
    APPEAL_OPEN_STATUSES,
    APPEAL_STATUS_ACCEPTED,
    APPEAL_STATUS_PARTIALLY_ACCEPTED,
    APPEAL_STATUS_PENDING,
    APPEAL_STATUS_REJECTED,
    COMPONENT_III_B,
    BLOCKER_INTERNAL_WARNING,
    BLOCKER_SEVERE_VIOLATION,
    CYCLE_STATUS_LOCKED,
    EVIDENCE_STATUS_VERIFIED,
    MEMBER_EVALUATION_STATUS_APPROVED,
    MEMBER_EVALUATION_STATUS_DRAFT,
    MEMBER_EVALUATION_STATUS_LOCKED,
)
from app.models import (
    DisciplineCase,
    EvaluationAppeal,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationEvidence,
    EvaluationEvidenceAppliedEvent,
    EvaluationScoreEvent,
    Member,
    MemberCycleRole,
    MemberEvaluation,
    MemberEvaluationBreakdown,
)
from app.services.evaluation_errors import EvaluationNotFoundError
from app.services.evaluation_evidence import EvidenceValidationService
from app.services.evaluation_report_cache import EvaluationReportCacheService

REPORT_VERSION = "phase6-v1"


def _load_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _round(value: float | None) -> float:
    return round(float(value or 0.0), 2)


def _attendance_percent(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    return numeric * 100 if 0 <= numeric <= 1 else numeric


class EvaluationReportService:
    def __init__(self, db: Session):
        self.db = db

    def get_cycle_dashboard(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        cycle = self._cycle(cycle_id)
        cache_key = EvaluationReportCacheService.make_key(
            cycle_id=cycle_id, report_type="dashboard", filters=filters
        )
        if cycle.status == CYCLE_STATUS_LOCKED:
            cached = EvaluationReportCacheService.get(cache_key)
            if cached:
                return cached

        rows = self._member_rows(cycle_id, filters)
        total_members = len(rows)
        total_scores = [row["evaluation"].total_score for row in rows]
        payload = {
            "cycleId": cycle.id,
            "cycleCode": cycle.code,
            "cycleName": cycle.name,
            "status": cycle.status,
            "reportVersion": REPORT_VERSION,
            "generatedAt": datetime.now(UTC),
            "totalMembers": total_members,
            "computedMembers": sum(
                row["evaluation"].status != MEMBER_EVALUATION_STATUS_DRAFT for row in rows
            ),
            "approvedMembers": sum(
                row["evaluation"].status
                in {MEMBER_EVALUATION_STATUS_APPROVED, MEMBER_EVALUATION_STATUS_LOCKED}
                or row["evaluation"].approved_at is not None
                for row in rows
            ),
            "lockedMembers": sum(
                row["evaluation"].status == MEMBER_EVALUATION_STATUS_LOCKED for row in rows
            ),
            "averageTotalScore": _round(mean(total_scores) if total_scores else 0.0),
            "classificationDistribution": self.get_classification_distribution(
                cycle_id, filters
            )["classificationDistribution"],
            "componentAverages": self.get_component_averages(cycle_id, filters)[
                "componentAverages"
            ],
            "riskSummary": self.get_risk_report(cycle_id, filters)["summary"],
            "unitDistribution": self._unit_distribution(rows),
            "openAppeals": self._count_open_appeals(cycle_id, filters),
            "missingEvidenceEvents": self._count_missing_evidence_events(cycle_id, filters),
            "invalidWeightMembers": self._count_invalid_weight_members(cycle_id, filters),
        }
        return EvaluationReportCacheService.set_if_cacheable(cache_key, cycle, payload)

    def get_cycle_summary(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        dashboard = self.get_cycle_dashboard(cycle_id, filters)
        return {
            key: dashboard[key]
            for key in (
                "cycleId",
                "cycleCode",
                "cycleName",
                "status",
                "totalMembers",
                "computedMembers",
                "approvedMembers",
                "lockedMembers",
                "averageTotalScore",
                "classificationDistribution",
                "cache",
            )
            if key in dashboard
        }

    def get_classification_distribution(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        rows = self._member_rows(cycle_id, filters)
        distribution = Counter(
            row["evaluation"].final_classification or "UNCLASSIFIED" for row in rows
        )
        return {"cycleId": cycle_id, "classificationDistribution": dict(distribution)}

    def get_component_averages(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        rows = self._member_rows(cycle_id, filters)
        evaluations = [row["evaluation"] for row in rows]
        return {
            "cycleId": cycle_id,
            "componentAverages": {
                "I": _round(mean([row.component_i_score for row in evaluations]) if evaluations else 0),
                "II": _round(mean([row.component_ii_score for row in evaluations]) if evaluations else 0),
                "III_A": _round(
                    mean([row.component_iii_a_score for row in evaluations])
                    if evaluations
                    else 0
                ),
                "III_B": _round(
                    mean([row.component_iii_b_score for row in evaluations])
                    if evaluations
                    else 0
                ),
            },
        }

    def get_member_report(self, cycle_id: str, member_id: str) -> dict[str, Any]:
        cycle = self._cycle(cycle_id)
        row = self.db.scalar(
            select(MemberEvaluation).where(
                MemberEvaluation.cycle_id == cycle_id,
                MemberEvaluation.member_id == member_id,
            )
        )
        member = self.db.get(Member, member_id)
        if not row or not member:
            raise EvaluationNotFoundError("Evaluation report not found")

        return {
            "cycleId": cycle.id,
            "cycleCode": cycle.code,
            "cycleName": cycle.name,
            "status": cycle.status,
            "reportVersion": REPORT_VERSION,
            "generatedAt": datetime.now(UTC),
            "member": self._member_out(member, cycle_id),
            "scores": self._scores_out(row),
            "classification": {
                "preliminary": row.preliminary_classification,
                "final": row.final_classification,
            },
            "blockers": _load_json(row.blockers_json, []),
            "breakdowns": self.get_member_breakdowns(cycle_id, member_id),
            "evidence": [
                self._evidence_out(item)
                for item in self.db.scalars(
                    self._member_evidence_stmt(cycle_id=cycle_id, member_id=member_id).order_by(
                        EvaluationEvidence.created_at
                    )
                ).all()
            ],
            "appeals": [
                self._appeal_out(item)
                for item in self.db.scalars(
                    select(EvaluationAppeal)
                    .where(
                        EvaluationAppeal.cycle_id == cycle_id,
                        EvaluationAppeal.member_id == member_id,
                    )
                    .order_by(EvaluationAppeal.created_at)
                ).all()
            ],
            "disciplineCases": [
                self._discipline_case_out(item)
                for item in self.db.scalars(
                    select(DisciplineCase)
                    .where(
                        DisciplineCase.cycle_id == cycle_id,
                        DisciplineCase.member_id == member_id,
                    )
                    .order_by(DisciplineCase.created_at)
                ).all()
            ],
        }

    def get_member_breakdowns(self, cycle_id: str, member_id: str) -> list[dict[str, Any]]:
        member_unit_codes = self._member_unit_codes(cycle_id, member_id)
        rows = self.db.scalars(
            select(MemberEvaluationBreakdown)
            .where(
                MemberEvaluationBreakdown.cycle_id == cycle_id,
                MemberEvaluationBreakdown.member_id == member_id,
            )
            .order_by(
                MemberEvaluationBreakdown.component,
                MemberEvaluationBreakdown.criterion_code,
            )
        ).all()

        filtered_rows = []
        for row in rows:
            if row.component == COMPONENT_III_B and (
                not row.unit_code or row.unit_code not in member_unit_codes
            ):
                continue
            filtered_rows.append(self._breakdown_out(row))

        return filtered_rows

    def _member_evidence_stmt(self, *, cycle_id: str, member_id: str):
        member_events = select(EvaluationScoreEvent.id, EvaluationScoreEvent.criterion_id).where(
            EvaluationScoreEvent.cycle_id == cycle_id,
            EvaluationScoreEvent.member_id == member_id,
        ).subquery()
        member_event_ids = select(member_events.c.id)
        member_criterion_ids = select(member_events.c.criterion_id).where(
            member_events.c.criterion_id.is_not(None)
        )

        return (
            select(EvaluationEvidence)
            .where(
                EvaluationEvidence.cycle_id == cycle_id,
                or_(
                    EvaluationEvidence.member_id == member_id,
                    EvaluationEvidence.score_event_id.in_(member_event_ids),
                    and_(
                        EvaluationEvidence.score_event_id.is_(None),
                        ~EvaluationEvidence.applied_events.any(),
                        EvaluationEvidence.criterion_id.in_(member_criterion_ids),
                    ),
                    exists(
                        select(1).where(
                            and_(
                                EvaluationEvidenceAppliedEvent.evidence_id == EvaluationEvidence.id,
                                EvaluationEvidenceAppliedEvent.score_event_id.in_(member_event_ids),
                            )
                        )
                    ),
                ),
            )
        )

    def get_unit_report(
        self, cycle_id: str, unit_code: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        merged_filters = dict(filters or {})
        merged_filters["unitCode"] = unit_code
        rows = self._member_rows(cycle_id, merged_filters)
        scores = [row["evaluation"].total_score for row in rows]
        return {
            "cycleId": cycle_id,
            "unitCode": unit_code,
            "totalMembers": len(rows),
            "averageTotalScore": _round(mean(scores) if scores else 0.0),
            "classificationDistribution": self.get_classification_distribution(
                cycle_id, merged_filters
            )["classificationDistribution"],
            "componentAverages": self.get_component_averages(cycle_id, merged_filters)[
                "componentAverages"
            ],
            "appealCount": self._count_appeals(cycle_id, merged_filters),
            "disciplineCaseCount": self._count_discipline_cases(cycle_id, merged_filters),
            "riskMembers": [
                self._member_score_row_out(row)
                for row in rows
                if self._is_risk_evaluation(row["evaluation"])
            ],
            "topMembers": [
                self._member_score_row_out(row)
                for row in sorted(
                    rows, key=lambda item: item["evaluation"].total_score, reverse=True
                )[:10]
            ],
            "members": [self._member_score_row_out(row) for row in rows],
        }

    def get_units_report(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        rows = self._member_rows(cycle_id, filters)
        unit_codes = sorted({row["unitCode"] or "UNASSIGNED" for row in rows})
        return {
            "cycleId": cycle_id,
            "units": [
                self.get_unit_report(cycle_id, unit_code, filters)
                for unit_code in unit_codes
            ],
        }

    def get_risk_report(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        rows = self._member_rows(cycle_id, filters)
        cases = self._discipline_cases_for_rows(cycle_id, rows)
        blocker_counter: Counter[str] = Counter()
        risk_members = []
        for row in rows:
            blockers = _load_json(row["evaluation"].blockers_json, [])
            for blocker in blockers:
                if isinstance(blocker, dict):
                    blocker_counter[blocker.get("code") or blocker.get("blockerCode") or "UNKNOWN"] += 1
                else:
                    blocker_counter[str(blocker)] += 1
            if self._is_risk_evaluation(row["evaluation"]):
                risk_members.append(self._member_score_row_out(row))

        return {
            "cycleId": cycle_id,
            "summary": {
                "attendanceUnder80": sum(
                    (_attendance_percent(row["evaluation"].attendance_rate) or 100) < 80
                    for row in rows
                ),
                "internalWarnings": sum(
                    case.blocker_code == BLOCKER_INTERNAL_WARNING for case in cases
                )
                + blocker_counter.get(BLOCKER_INTERNAL_WARNING, 0),
                "severeViolations": sum(
                    case.blocker_code == BLOCKER_SEVERE_VIOLATION for case in cases
                )
                + blocker_counter.get(BLOCKER_SEVERE_VIOLATION, 0),
                "openAppeals": self._count_open_appeals(cycle_id, filters),
                "disciplineCases": len(cases),
                "blockers": dict(blocker_counter),
            },
            "riskMembers": risk_members,
            "disciplineCases": [self._discipline_case_out(case) for case in cases],
        }

    def get_appeal_report(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        appeals = self._appeals_for_filters(cycle_id, filters)
        status_counter = Counter(appeal.status for appeal in appeals)
        type_counter = Counter(appeal.appeal_type for appeal in appeals)
        resolution_hours = []
        for appeal in appeals:
            if appeal.resolved_at and appeal.created_at:
                resolution_hours.append(
                    (appeal.resolved_at - appeal.created_at).total_seconds() / 3600
                )
        return {
            "cycleId": cycle_id,
            "totalAppeals": len(appeals),
            "pendingAppeals": status_counter.get(APPEAL_STATUS_PENDING, 0),
            "openAppeals": sum(status_counter.get(status, 0) for status in APPEAL_OPEN_STATUSES),
            "acceptedAppeals": status_counter.get(APPEAL_STATUS_ACCEPTED, 0),
            "partiallyAcceptedAppeals": status_counter.get(
                APPEAL_STATUS_PARTIALLY_ACCEPTED, 0
            ),
            "rejectedAppeals": status_counter.get(APPEAL_STATUS_REJECTED, 0),
            "averageResolutionHours": _round(
                mean(resolution_hours) if resolution_hours else 0.0
            ),
            "appealsByType": dict(type_counter),
            "appealsByStatus": dict(status_counter),
            "appealsByUnit": self._appeals_by_unit(cycle_id, appeals),
        }

    def get_member_export_rows(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self._cycle(cycle_id)
        return [self._member_score_row_out(row) for row in self._member_rows(cycle_id, filters)]

    def _cycle(self, cycle_id: str) -> EvaluationCycle:
        cycle = self.db.get(EvaluationCycle, cycle_id)
        if not cycle:
            raise EvaluationNotFoundError("Evaluation cycle not found")
        return cycle

    def _member_rows(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        rows = self.db.execute(
            select(MemberEvaluation, Member)
            .join(Member, Member.id == MemberEvaluation.member_id)
            .where(MemberEvaluation.cycle_id == cycle_id)
            .order_by(Member.name)
        ).all()
        output = []
        for evaluation, member in rows:
            primary_role = self._primary_role(cycle_id, member.id)
            unit_code = primary_role.unit_code if primary_role else member.ban
            role_title = primary_role.role_title if primary_role else member.role_title
            item = {
                "evaluation": evaluation,
                "member": member,
                "unitCode": unit_code,
                "roleTitle": role_title,
            }
            if self._matches_filters(item, filters):
                output.append(item)
        return output

    def _matches_filters(self, item: dict[str, Any], filters: dict[str, Any]) -> bool:
        evaluation = item["evaluation"]
        member = item["member"]
        if filters.get("unitCode") and (item["unitCode"] or "UNASSIGNED") != filters["unitCode"]:
            return False
        if filters.get("classification") and evaluation.final_classification != filters["classification"]:
            return False
        if filters.get("status") and evaluation.status != filters["status"]:
            return False
        if filters.get("minScore") is not None and evaluation.total_score < float(filters["minScore"]):
            return False
        if filters.get("maxScore") is not None and evaluation.total_score > float(filters["maxScore"]):
            return False
        if filters.get("hasBlocker") is not None:
            has_blocker = bool(_load_json(evaluation.blockers_json, []))
            if has_blocker != bool(filters["hasBlocker"]):
                return False
        if filters.get("hasAppeal") is not None:
            has_appeal = self._count_appeals_for_member(evaluation.cycle_id, member.id) > 0
            if has_appeal != bool(filters["hasAppeal"]):
                return False
        if filters.get("hasDisciplineCase") is not None:
            has_case = self._count_discipline_cases_for_member(evaluation.cycle_id, member.id) > 0
            if has_case != bool(filters["hasDisciplineCase"]):
                return False
        search = (filters.get("search") or "").strip().lower()
        if search and search not in (member.name or "").lower() and search not in (member.mssv or "").lower():
            return False
        return True

    def _primary_role(self, cycle_id: str, member_id: str) -> MemberCycleRole | None:
        roles = self.db.scalars(
            select(MemberCycleRole)
            .where(
                MemberCycleRole.cycle_id == cycle_id,
                MemberCycleRole.member_id == member_id,
            )
            .order_by(MemberCycleRole.is_primary.desc(), MemberCycleRole.unit_code)
        ).all()
        return roles[0] if roles else None

    def _member_unit_codes(self, cycle_id: str, member_id: str) -> set[str]:
        return {
            role.unit_code
            for role in self.db.scalars(
                select(MemberCycleRole).where(
                    MemberCycleRole.cycle_id == cycle_id,
                    MemberCycleRole.member_id == member_id,
                )
            ).all()
            if role.unit_code
        }

    def _member_out(self, member: Member, cycle_id: str) -> dict[str, Any]:
        primary_role = self._primary_role(cycle_id, member.id)
        return {
            "id": member.id,
            "mssv": member.mssv,
            "name": member.name,
            "ban": member.ban,
            "unitCode": primary_role.unit_code if primary_role else member.ban,
            "roleTitle": primary_role.role_title if primary_role else member.role_title,
            "status": member.status,
        }

    def _scores_out(self, row: MemberEvaluation) -> dict[str, Any]:
        return {
            "componentI": row.component_i_score,
            "componentII": row.component_ii_score,
            "componentIIIa": row.component_iii_a_score,
            "componentIIIb": row.component_iii_b_score,
            "total": row.total_score,
            "attendanceRate": row.attendance_rate,
        }

    def _member_score_row_out(self, item: dict[str, Any]) -> dict[str, Any]:
        row = item["evaluation"]
        member = item["member"]
        return {
            "cycleId": row.cycle_id,
            "memberEvaluationId": row.id,
            "memberId": member.id,
            "mssv": member.mssv,
            "name": member.name,
            "unitCode": item["unitCode"],
            "roleTitle": item["roleTitle"],
            "componentIScore": row.component_i_score,
            "componentIIScore": row.component_ii_score,
            "componentIIIAScore": row.component_iii_a_score,
            "componentIIIBScore": row.component_iii_b_score,
            "totalScore": row.total_score,
            "preliminaryClassification": row.preliminary_classification,
            "finalClassification": row.final_classification,
            "attendanceRate": row.attendance_rate,
            "blockers": _load_json(row.blockers_json, []),
            "status": row.status,
            "appealCount": self._count_appeals_for_member(row.cycle_id, member.id),
            "disciplineCaseCount": self._count_discipline_cases_for_member(
                row.cycle_id, member.id
            ),
        }

    def _breakdown_out(self, row: MemberEvaluationBreakdown) -> dict[str, Any]:
        return {
            "id": row.id,
            "criterionCode": row.criterion_code,
            "component": row.component,
            "unitCode": row.unit_code,
            "rawScore": row.raw_score,
            "finalScore": row.final_score,
            "maxScoreSnapshot": row.max_score_snapshot,
            "capApplied": row.cap_applied,
            "evidenceCount": row.evidence_count,
            "calculationNote": row.calculation_note,
        }

    def _evidence_out(self, row: EvaluationEvidence) -> dict[str, Any]:
        return {
            "id": row.id,
            "criterionId": row.criterion_id,
            "scoreEventId": row.score_event_id,
            "evidenceType": row.evidence_type,
            "title": row.title,
            "url": row.url,
            "filePath": row.file_path,
            "description": row.description,
            "capturedAt": row.captured_at,
            "status": row.status,
        }

    def _appeal_out(self, row: EvaluationAppeal) -> dict[str, Any]:
        return {
            "id": row.id,
            "criterionCode": row.criterion_code,
            "appealType": row.appeal_type,
            "content": row.content,
            "requestedScore": row.requested_score,
            "status": row.status,
            "resolvedAt": row.resolved_at,
            "resolutionNote": row.resolution_note,
        }

    def _discipline_case_out(self, row: DisciplineCase) -> dict[str, Any]:
        return {
            "id": row.id,
            "memberId": row.member_id,
            "caseCode": row.case_code,
            "caseType": row.case_type,
            "severity": row.severity,
            "status": row.status,
            "title": row.title,
            "blockerCode": row.blocker_code,
            "pointImpact": row.point_impact,
            "createdAt": row.created_at,
            "resolvedAt": row.resolved_at,
        }

    def _unit_distribution(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        return dict(Counter(row["unitCode"] or "UNASSIGNED" for row in rows))

    def _is_risk_evaluation(self, row: MemberEvaluation) -> bool:
        blockers = _load_json(row.blockers_json, [])
        blocker_codes = {
            item.get("code") or item.get("blockerCode") if isinstance(item, dict) else str(item)
            for item in blockers
        }
        attendance = _attendance_percent(row.attendance_rate)
        return (
            row.final_classification in {"NEEDS_IMPROVEMENT", "FAILED"}
            or bool(blocker_codes)
            or (attendance is not None and attendance < 80)
        )

    def _count_open_appeals(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> int:
        return sum(
            appeal.status in APPEAL_OPEN_STATUSES
            for appeal in self._appeals_for_filters(cycle_id, filters)
        )

    def _count_appeals(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> int:
        return len(self._appeals_for_filters(cycle_id, filters))

    def _count_appeals_for_member(self, cycle_id: str, member_id: str) -> int:
        return self.db.scalar(
            select(func.count()).select_from(EvaluationAppeal).where(
                EvaluationAppeal.cycle_id == cycle_id,
                EvaluationAppeal.member_id == member_id,
            )
        ) or 0

    def _count_discipline_cases(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> int:
        return len(self._discipline_cases_for_rows(cycle_id, self._member_rows(cycle_id, filters)))

    def _count_discipline_cases_for_member(self, cycle_id: str, member_id: str) -> int:
        return self.db.scalar(
            select(func.count()).select_from(DisciplineCase).where(
                DisciplineCase.cycle_id == cycle_id,
                DisciplineCase.member_id == member_id,
            )
        ) or 0

    def _count_missing_evidence_events(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> int:
        member_ids = {row["member"].id for row in self._member_rows(cycle_id, filters)}
        if not member_ids:
            return 0
        events = self.db.execute(
            select(EvaluationScoreEvent, EvaluationCriterion)
            .join(EvaluationCriterion, EvaluationCriterion.id == EvaluationScoreEvent.criterion_id)
            .where(
                EvaluationScoreEvent.cycle_id == cycle_id,
                EvaluationScoreEvent.member_id.in_(member_ids),
                EvaluationScoreEvent.is_void.is_(False),
                EvaluationCriterion.requires_evidence.is_(True),
            )
        ).all()
        if not events:
            return 0

        evidence_counts = EvidenceValidationService(self.db).count_effective_evidence_for_events(
            (event for event, _criterion in events),
            mode="approval",
        )
        return sum(1 for event, _criterion in events if not evidence_counts.get(event.id, 0))

    def _count_invalid_weight_members(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> int:
        rows = self._member_rows(cycle_id, filters)
        invalid = 0
        for row in rows:
            roles = self.db.scalars(
                select(MemberCycleRole).where(
                    MemberCycleRole.cycle_id == cycle_id,
                    MemberCycleRole.member_id == row["member"].id,
                )
            ).all()
            if roles and abs(sum(role.participation_weight for role in roles) - 1.0) > 0.001:
                invalid += 1
        return invalid

    def _appeals_for_filters(
        self, cycle_id: str, filters: dict[str, Any] | None = None
    ) -> list[EvaluationAppeal]:
        member_ids = {row["member"].id for row in self._member_rows(cycle_id, filters)}
        if not member_ids:
            return []
        return self.db.scalars(
            select(EvaluationAppeal).where(
                EvaluationAppeal.cycle_id == cycle_id,
                EvaluationAppeal.member_id.in_(member_ids),
            )
        ).all()

    def _discipline_cases_for_rows(
        self, cycle_id: str, rows: list[dict[str, Any]]
    ) -> list[DisciplineCase]:
        member_ids = {row["member"].id for row in rows}
        if not member_ids:
            return []
        return self.db.scalars(
            select(DisciplineCase).where(
                DisciplineCase.cycle_id == cycle_id,
                DisciplineCase.member_id.in_(member_ids),
            )
        ).all()

    def _appeals_by_unit(
        self, cycle_id: str, appeals: list[EvaluationAppeal]
    ) -> dict[str, int]:
        counts: defaultdict[str, int] = defaultdict(int)
        for appeal in appeals:
            member = self.db.get(Member, appeal.member_id)
            if not member:
                continue
            role = self._primary_role(cycle_id, member.id)
            counts[(role.unit_code if role else member.ban) or "UNASSIGNED"] += 1
        return dict(counts)
