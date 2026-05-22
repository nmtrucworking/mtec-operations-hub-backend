import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.discipline_levels import (
    DISCIPLINE_LEVEL_EXPULSION,
    DISCIPLINE_LEVEL_NONE,
    DISCIPLINE_LEVEL_REMINDER,
    DISCIPLINE_LEVEL_SUSPENSION,
    DISCIPLINE_LEVEL_WARNING_1,
    DISCIPLINE_LEVEL_WARNING_2,
    normalize_discipline_level,
)
from app.core.evaluation_constants import (
    BLOCKER_INTERNAL_WARNING,
    BLOCKER_SEVERE_VIOLATION,
    CYCLE_MUTABLE_STATUSES,
    DEFAULT_ATTENDANCE_PENALTY_CRITERION_CODE,
    DEFAULT_COMPETITION_BONUS_CRITERION_CODE,
    EVENT_TYPE_BONUS,
    EVENT_TYPE_LEGACY_IMPORT,
    EVIDENCE_STATUS_PENDING,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_TYPE_LEGACY_SUMMARY,
    MIGRATION_SOURCE_MODULE_DISCIPLINE_LEGACY,
    MIGRATION_VERSION_PHASE5,
    SOURCE_TYPE_ATTENDANCE_AGGREGATE,
    SOURCE_TYPE_COMPETITION_RESULT,
    SOURCE_TYPE_LEGACY_DISCIPLINE_KPI,
    SOURCE_TYPE_LEGACY_DISCIPLINE_RECORD,
)
from app.models import (
    Attendance,
    Competition,
    CompetitionResult,
    DisciplineCase,
    DisciplineRecord,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationEvidence,
    EvaluationScoreEvent,
    Meeting,
    Member,
)
from app.services.evaluation_errors import (
    EvaluationCycleLockedError,
    EvaluationMissingCriteriaError,
    EvaluationNotFoundError,
)

MIGRATION_MODES = {"dry_run", "sandbox", "production"}
MIGRATED_SCORE_EVENT_SOURCE_TYPES = {
    SOURCE_TYPE_ATTENDANCE_AGGREGATE,
    SOURCE_TYPE_COMPETITION_RESULT,
    SOURCE_TYPE_LEGACY_DISCIPLINE_RECORD,
}


@dataclass
class MigrationSummary:
    mode: str
    cycle_id: str | None = None
    migration_batch_id: str | None = None
    processed: int = 0
    created_score_events: int = 0
    created_discipline_cases: int = 0
    created_evidence: int = 0
    skipped: int = 0
    failed: int = 0
    warnings: list[dict[str, Any]] = field(default_factory=list)
    manual_review_queue: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "cycleId": self.cycle_id,
            "migrationBatchId": self.migration_batch_id,
            "processed": self.processed,
            "createdScoreEvents": self.created_score_events,
            "createdDisciplineCases": self.created_discipline_cases,
            "createdEvidence": self.created_evidence,
            "skipped": self.skipped,
            "failed": self.failed,
            "warnings": self.warnings,
            "manualReviewQueue": self.manual_review_queue,
        }


def generate_migration_batch_id(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"eval-legacy-{now.strftime('%Y%m%d-%H%M%S')}"


def metadata_dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def metadata_load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {"legacyValue": value}
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def normalize_legacy_level(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    replacements = {
        "ô": "o",
        "ơ": "o",
        "ớ": "o",
        "ờ": "o",
        "ở": "o",
        "ỡ": "o",
        "ợ": "o",
        "ă": "a",
        "ắ": "a",
        "ằ": "a",
        "ẳ": "a",
        "ẵ": "a",
        "ặ": "a",
        "â": "a",
        "ấ": "a",
        "ầ": "a",
        "ẩ": "a",
        "ẫ": "a",
        "ậ": "a",
        "á": "a",
        "à": "a",
        "ả": "a",
        "ã": "a",
        "ạ": "a",
        "é": "e",
        "è": "e",
        "ẻ": "e",
        "ẽ": "e",
        "ẹ": "e",
        "ê": "e",
        "ế": "e",
        "ề": "e",
        "ể": "e",
        "ễ": "e",
        "ệ": "e",
        "í": "i",
        "ì": "i",
        "ỉ": "i",
        "ĩ": "i",
        "ị": "i",
        "ó": "o",
        "ò": "o",
        "ỏ": "o",
        "õ": "o",
        "ọ": "o",
        "ú": "u",
        "ù": "u",
        "ủ": "u",
        "ũ": "u",
        "ụ": "u",
        "ư": "u",
        "ứ": "u",
        "ừ": "u",
        "ử": "u",
        "ữ": "u",
        "ự": "u",
        "ý": "y",
        "ỳ": "y",
        "ỷ": "y",
        "ỹ": "y",
        "ỵ": "y",
        "đ": "d",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return " ".join(normalized.split())


def map_discipline_level(value: str | None) -> dict[str, Any] | None:
    try:
        canonical = normalize_discipline_level(value)
    except ValueError:
        canonical = None
    if canonical == DISCIPLINE_LEVEL_NONE:
        return None
    if canonical == DISCIPLINE_LEVEL_REMINDER:
        return {
            "caseType": "REMINDER",
            "severity": "LOW",
            "blockerCode": None,
            "requiresManualReview": False,
            "confidence": "HIGH",
        }
    if canonical in {DISCIPLINE_LEVEL_WARNING_1, DISCIPLINE_LEVEL_WARNING_2}:
        return {
            "caseType": "WARNING",
            "severity": "MEDIUM",
            "blockerCode": BLOCKER_INTERNAL_WARNING,
            "requiresManualReview": False,
            "confidence": "HIGH",
        }
    if canonical == DISCIPLINE_LEVEL_SUSPENSION:
        return {
            "caseType": "SUSPENSION",
            "severity": "HIGH",
            "blockerCode": BLOCKER_SEVERE_VIOLATION,
            "requiresManualReview": False,
            "confidence": "HIGH",
        }
    if canonical == DISCIPLINE_LEVEL_EXPULSION:
        return {
            "caseType": "EXPULSION_REVIEW",
            "severity": "CRITICAL",
            "blockerCode": BLOCKER_SEVERE_VIOLATION,
            "requiresManualReview": False,
            "confidence": "HIGH",
        }

    normalized = normalize_legacy_level(value)
    if normalized in {"", "khong", "none", "n/a"}:
        return None
    if "nhac nho" in normalized:
        return {
            "caseType": "REMINDER",
            "severity": "LOW",
            "blockerCode": None,
            "requiresManualReview": False,
            "confidence": "MEDIUM",
        }
    if "canh cao" in normalized:
        return {
            "caseType": "WARNING",
            "severity": "MEDIUM",
            "blockerCode": BLOCKER_INTERNAL_WARNING,
            "requiresManualReview": False,
            "confidence": "MEDIUM",
        }
    if "dinh chi" in normalized:
        return {
            "caseType": "SUSPENSION",
            "severity": "HIGH",
            "blockerCode": BLOCKER_SEVERE_VIOLATION,
            "requiresManualReview": False,
            "confidence": "MEDIUM",
        }
    if "khai tru" in normalized or "xem xet khai tru" in normalized:
        return {
            "caseType": "EXPULSION_REVIEW",
            "severity": "CRITICAL",
            "blockerCode": BLOCKER_SEVERE_VIOLATION,
            "requiresManualReview": False,
            "confidence": "MEDIUM",
        }
    return {
        "caseType": "LEGACY_OTHER",
        "severity": "MEDIUM",
        "blockerCode": None,
        "requiresManualReview": True,
        "confidence": "LOW",
    }


class EvaluationLegacyMigrationService:
    def __init__(self, db: Session):
        self.db = db

    def build_inventory(self) -> dict[str, Any]:
        discipline_total = self._count(DisciplineRecord)
        discipline_with_member_id = self._count_where(
            DisciplineRecord, DisciplineRecord.member_id.is_not(None)
        )
        unmatched = self._find_unmatched_discipline_records()
        inventory = {
            "disciplineRecords": {
                "total": discipline_total,
                "withMemberId": discipline_with_member_id,
                "withoutMemberId": discipline_total - discipline_with_member_id,
                "disciplineLevelDistribution": self._distribution(
                    DisciplineRecord.discipline_level
                ),
                "absents": self._numeric_stats(DisciplineRecord.absents),
                "kpi": self._numeric_stats(DisciplineRecord.kpi),
                "unmatchedRecords": unmatched,
            },
            "attendances": {
                "total": self._count(Attendance),
                "statusDistribution": self._distribution(Attendance.status),
                "meetingCount": self._count_distinct(Attendance.meeting_id),
                "memberCount": self._count_distinct(Attendance.member_id),
            },
            "meetings": {
                "total": self._count(Meeting),
                "typeDistribution": self._distribution(Meeting.meeting_type),
                "statusDistribution": self._distribution(Meeting.status),
                "dateRange": self._date_range(Meeting.date),
            },
            "competitions": {
                "total": self._count(Competition),
                "statusDistribution": self._distribution(Competition.status),
                "scaleDistribution": self._distribution(Competition.scale),
            },
            "competitionResults": {
                "total": self._count(CompetitionResult),
                "syncedCount": self._count_where(
                    CompetitionResult, CompetitionResult.is_synced.is_(True)
                ),
                "bonusKpiTotal": float(
                    self.db.scalar(select(func.coalesce(func.sum(CompetitionResult.bonus_kpi), 0)))
                    or 0
                ),
                "achievementDistribution": self._distribution(
                    CompetitionResult.achievement
                ),
            },
            "members": {
                "activeCount": self._count_where(Member, Member.status == "Active"),
                "unitDistribution": self._distribution(Member.ban),
            },
        }
        create_audit_log(
            db=self.db,
            action="LEGACY_INVENTORY_DISCIPLINE",
            resource_type="evaluation_migration",
            resource_id="inventory",
            after_snapshot={
                "disciplineRecords": discipline_total,
                "attendances": inventory["attendances"]["total"],
                "competitionResults": inventory["competitionResults"]["total"],
            },
        )
        return inventory

    def migrate(
        self,
        cycle_id: str,
        *,
        mode: str = "dry_run",
        migration_batch_id: str | None = None,
        member_id: str | None = None,
        batch_size: int | None = None,
    ) -> dict[str, Any]:
        if mode not in MIGRATION_MODES:
            raise ValueError(f"Unsupported migration mode: {mode}")
        dry_run = mode == "dry_run"
        batch_id = migration_batch_id or generate_migration_batch_id()
        cycle = self._load_cycle(cycle_id)
        summary = MigrationSummary(
            mode=mode,
            cycle_id=cycle_id,
            migration_batch_id=batch_id,
        )
        self._audit_batch("LEGACY_MIGRATION_DRY_RUN" if dry_run else "LEGACY_MIGRATION_START", summary)

        self._migrate_discipline_records(
            cycle=cycle,
            summary=summary,
            dry_run=dry_run,
            member_id=member_id,
            batch_size=batch_size,
        )
        self._migrate_attendance_records(
            cycle=cycle,
            summary=summary,
            dry_run=dry_run,
            member_id=member_id,
            batch_size=batch_size,
        )
        self._migrate_competition_results(
            cycle=cycle,
            summary=summary,
            dry_run=dry_run,
            member_id=member_id,
            batch_size=batch_size,
        )
        self._audit_batch("LEGACY_MIGRATION_COMPLETE", summary)
        return summary.as_dict()

    def soft_rollback(self, migration_batch_id: str) -> dict[str, Any]:
        voided_events = 0
        cancelled_cases = 0
        rejected_evidence = 0

        events = self.db.scalars(
            select(EvaluationScoreEvent).where(
                EvaluationScoreEvent.source_type.in_(MIGRATED_SCORE_EVENT_SOURCE_TYPES),
                EvaluationScoreEvent.is_void.is_(False),
            )
        ).all()
        for event in events:
            if metadata_load(event.metadata_json).get("migrationBatchId") != migration_batch_id:
                continue
            event.is_void = True
            event.void_reason = f"Rolled back migration batch {migration_batch_id}"
            voided_events += 1

        cases = self.db.scalars(
            select(DisciplineCase).where(
                DisciplineCase.source_type == SOURCE_TYPE_LEGACY_DISCIPLINE_RECORD,
                DisciplineCase.status != "CANCELLED",
            )
        ).all()
        for case in cases:
            if metadata_load(case.metadata_json).get("migrationBatchId") != migration_batch_id:
                continue
            case.status = "CANCELLED"
            case.resolution_note = f"Rolled back migration batch {migration_batch_id}"
            cancelled_cases += 1

        evidences = self.db.scalars(
            select(EvaluationEvidence).where(
                EvaluationEvidence.evidence_type == EVIDENCE_TYPE_LEGACY_SUMMARY,
                EvaluationEvidence.status != EVIDENCE_STATUS_REJECTED,
            )
        ).all()
        for evidence in evidences:
            metadata = metadata_load(evidence.metadata_json)
            if metadata.get("migrationBatchId") != migration_batch_id:
                continue
            metadata["rolledBack"] = True
            evidence.metadata_json = metadata_dump(metadata)
            evidence.status = EVIDENCE_STATUS_REJECTED
            rejected_evidence += 1

        result = {
            "migrationBatchId": migration_batch_id,
            "voidedScoreEvents": voided_events,
            "cancelledDisciplineCases": cancelled_cases,
            "rejectedEvidence": rejected_evidence,
        }
        create_audit_log(
            db=self.db,
            action="LEGACY_MIGRATION_ROLLBACK",
            resource_type="evaluation_migration",
            resource_id=migration_batch_id,
            after_snapshot=result,
        )
        return result

    def write_report(self, payload: dict[str, Any], output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".md":
            path.write_text(self.render_markdown_report(payload), encoding="utf-8")
            return
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def render_markdown_report(self, payload: dict[str, Any]) -> str:
        title = "Evaluation Legacy Migration Report"
        lines = [f"# {title}", ""]
        if "disciplineRecords" in payload:
            lines.extend(
                [
                    "## Inventory",
                    "",
                    f"- Discipline records: {payload['disciplineRecords']['total']}",
                    f"- Attendances: {payload['attendances']['total']}",
                    f"- Competition results: {payload['competitionResults']['total']}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "## Summary",
                    "",
                    f"- Mode: {payload.get('mode')}",
                    f"- Cycle ID: {payload.get('cycleId')}",
                    f"- Batch ID: {payload.get('migrationBatchId')}",
                    f"- Processed: {payload.get('processed')}",
                    f"- Created score events: {payload.get('createdScoreEvents')}",
                    f"- Created discipline cases: {payload.get('createdDisciplineCases')}",
                    f"- Created evidence: {payload.get('createdEvidence')}",
                    f"- Skipped: {payload.get('skipped')}",
                    f"- Failed: {payload.get('failed')}",
                    "",
                ]
            )
        warnings = payload.get("warnings") or []
        if warnings:
            lines.append("## Warnings")
            lines.append("")
            for item in warnings[:50]:
                lines.append(f"- `{item.get('code')}`: {item.get('message')}")
        manual_review = payload.get("manualReviewQueue") or []
        if manual_review:
            lines.append("")
            lines.append("## Manual Review Queue")
            lines.append("")
            for item in manual_review[:50]:
                lines.append(
                    f"- {item.get('sourceType')} `{item.get('sourceId')}`: {item.get('issueCode')}"
                )
        return "\n".join(lines) + "\n"

    def _migrate_discipline_records(
        self,
        *,
        cycle: EvaluationCycle,
        summary: MigrationSummary,
        dry_run: bool,
        member_id: str | None,
        batch_size: int | None,
    ) -> None:
        stmt = select(DisciplineRecord).order_by(DisciplineRecord.updated_at.desc())
        if member_id:
            stmt = stmt.where(DisciplineRecord.member_id == member_id)
        records = self.db.scalars(self._limit(stmt, batch_size)).all()
        absence_criterion = self._get_criterion(
            DEFAULT_ATTENDANCE_PENALTY_CRITERION_CODE,
            summary=summary,
            required=False,
        )
        for record in records:
            summary.processed += 1
            member = self._resolve_record_member(record)
            if not member:
                self._queue_manual_review(
                    summary,
                    source_type=SOURCE_TYPE_LEGACY_DISCIPLINE_RECORD,
                    source_id=record.id,
                    member_id=record.member_id,
                    mssv=record.mssv,
                    name=record.name,
                    issue_code="UNMATCHED_MEMBER",
                    issue_detail="Cannot match discipline record to member",
                    suggested_action="Match member_id or create member before migration",
                )
                summary.failed += 1
                continue

            if record.absents and record.absents > 0 and absence_criterion:
                self._create_score_event(
                    cycle=cycle,
                    member=member,
                    criterion=absence_criterion,
                    event_type=EVENT_TYPE_LEGACY_IMPORT,
                    source_type=SOURCE_TYPE_LEGACY_DISCIPLINE_RECORD,
                    source_id=record.id,
                    raw_value=float(record.absents),
                    score_delta=-float(record.absents),
                    note=f"Legacy absents summary: {record.absents}",
                    metadata={
                        "sourceTable": "discipline_records",
                        "sourceId": record.id,
                        "legacyField": "absents",
                        "confidence": "LOW",
                        "unverified": True,
                    },
                    summary=summary,
                    dry_run=dry_run,
                )

            mapping = map_discipline_level(record.discipline_level)
            if mapping:
                self._create_discipline_case(
                    cycle=cycle,
                    member=member,
                    record=record,
                    mapping=mapping,
                    summary=summary,
                    dry_run=dry_run,
                )

            if record.kpi and (record.kpi > 100 or record.kpi < 0):
                self._queue_manual_review(
                    summary,
                    source_type=SOURCE_TYPE_LEGACY_DISCIPLINE_KPI,
                    source_id=record.id,
                    member_id=member.id,
                    mssv=member.mssv,
                    name=member.name,
                    issue_code="LEGACY_KPI_OUT_OF_RANGE",
                    issue_detail=f"Legacy KPI is {record.kpi}",
                    suggested_action="Review KPI as reconciliation snapshot only",
                )

    def _migrate_attendance_records(
        self,
        *,
        cycle: EvaluationCycle,
        summary: MigrationSummary,
        dry_run: bool,
        member_id: str | None,
        batch_size: int | None,
    ) -> None:
        criterion = self._get_criterion(
            DEFAULT_ATTENDANCE_PENALTY_CRITERION_CODE,
            summary=summary,
            required=False,
        )
        if not criterion:
            return
        stmt = (
            select(Attendance.member_id, func.count())
            .where(Attendance.status == "Absent")
            .group_by(Attendance.member_id)
        )
        if member_id:
            stmt = stmt.where(Attendance.member_id == member_id)
        rows = self.db.execute(self._limit(stmt, batch_size)).all()
        for attendance_member_id, absent_count in rows:
            summary.processed += 1
            member = self.db.get(Member, attendance_member_id)
            if not member:
                self._queue_manual_review(
                    summary,
                    source_type=SOURCE_TYPE_ATTENDANCE_AGGREGATE,
                    source_id=f"{cycle.id}:{attendance_member_id}",
                    member_id=attendance_member_id,
                    mssv=None,
                    name=None,
                    issue_code="ATTENDANCE_MEMBER_NOT_FOUND",
                    issue_detail="Attendance references missing member",
                    suggested_action="Restore or map member before migration",
                )
                summary.failed += 1
                continue
            self._create_score_event(
                cycle=cycle,
                member=member,
                criterion=criterion,
                event_type=EVENT_TYPE_LEGACY_IMPORT,
                source_type=SOURCE_TYPE_ATTENDANCE_AGGREGATE,
                source_id=f"{cycle.id}:{member.id}:absent",
                raw_value=float(absent_count),
                score_delta=-float(absent_count),
                note=f"Legacy attendance aggregate: {absent_count} absent",
                metadata={
                    "sourceTable": "attendances",
                    "legacyField": "status",
                    "attendanceStatus": "Absent",
                    "confidence": "MEDIUM",
                },
                summary=summary,
                dry_run=dry_run,
            )

    def _migrate_competition_results(
        self,
        *,
        cycle: EvaluationCycle,
        summary: MigrationSummary,
        dry_run: bool,
        member_id: str | None,
        batch_size: int | None,
    ) -> None:
        criterion = self._get_criterion(
            DEFAULT_COMPETITION_BONUS_CRITERION_CODE,
            summary=summary,
            required=False,
        )
        if not criterion:
            return
        stmt = (
            select(CompetitionResult)
            .where(CompetitionResult.bonus_kpi > 0)
            .order_by(CompetitionResult.created_at.desc())
        )
        if member_id:
            stmt = stmt.where(CompetitionResult.member_id == member_id)
        rows = self.db.scalars(self._limit(stmt, batch_size)).all()
        for result in rows:
            summary.processed += 1
            member = self.db.get(Member, result.member_id)
            if not member:
                self._queue_manual_review(
                    summary,
                    source_type=SOURCE_TYPE_COMPETITION_RESULT,
                    source_id=result.id,
                    member_id=result.member_id,
                    mssv=None,
                    name=None,
                    issue_code="COMPETITION_MEMBER_NOT_FOUND",
                    issue_detail="Competition result references missing member",
                    suggested_action="Restore or map member before migration",
                )
                summary.failed += 1
                continue
            self._create_score_event(
                cycle=cycle,
                member=member,
                criterion=criterion,
                event_type=EVENT_TYPE_BONUS,
                source_type=SOURCE_TYPE_COMPETITION_RESULT,
                source_id=result.id,
                raw_value=float(result.bonus_kpi),
                score_delta=float(result.bonus_kpi),
                note=f"Legacy competition bonus: {result.achievement}",
                metadata={
                    "sourceTable": "competition_results",
                    "competitionId": result.competition_id,
                    "achievement": result.achievement,
                    "legacyBonusKpi": result.bonus_kpi,
                    "legacyIsSynced": result.is_synced,
                    "confidence": "MEDIUM",
                },
                summary=summary,
                dry_run=dry_run,
            )
            if result.bonus_kpi > criterion.max_score:
                self._queue_manual_review(
                    summary,
                    source_type=SOURCE_TYPE_COMPETITION_RESULT,
                    source_id=result.id,
                    member_id=member.id,
                    mssv=member.mssv,
                    name=member.name,
                    issue_code="COMPETITION_BONUS_EXCEEDS_CRITERION_CAP",
                    issue_detail=f"bonus_kpi={result.bonus_kpi}, criterion cap={criterion.max_score}",
                    suggested_action="Review cap effect after compute",
                )

    def _create_score_event(
        self,
        *,
        cycle: EvaluationCycle,
        member: Member,
        criterion: EvaluationCriterion,
        event_type: str,
        source_type: str,
        source_id: str,
        raw_value: float,
        score_delta: float,
        note: str,
        metadata: dict[str, Any],
        summary: MigrationSummary,
        dry_run: bool,
    ) -> EvaluationScoreEvent | None:
        existing = self.db.scalar(
            select(EvaluationScoreEvent).where(
                EvaluationScoreEvent.cycle_id == cycle.id,
                EvaluationScoreEvent.member_id == member.id,
                EvaluationScoreEvent.criterion_code == criterion.code,
                EvaluationScoreEvent.source_type == source_type,
                EvaluationScoreEvent.source_id == source_id,
                EvaluationScoreEvent.event_type == event_type,
            )
        )
        if existing:
            summary.skipped += 1
            if abs(existing.score_delta - score_delta) > 0.001:
                self._warn(
                    summary,
                    "CONFLICTING_LEGACY_MAPPING",
                    f"Existing score event differs for {source_type}:{source_id}",
                    sourceType=source_type,
                    sourceId=source_id,
                    existingScoreDelta=existing.score_delta,
                    mappedScoreDelta=score_delta,
                )
            return existing

        if dry_run:
            summary.created_score_events += 1
            summary.created_evidence += 1
            return None

        event_metadata = self._migration_metadata(
            summary,
            source_table=metadata.get("sourceTable"),
            source_id=source_id,
            extra=metadata,
        )
        event = EvaluationScoreEvent(
            cycle_id=cycle.id,
            member_id=member.id,
            criterion_id=criterion.id,
            criterion_code=criterion.code,
            component=criterion.component,
            unit_code=criterion.unit_code,
            event_type=event_type,
            source_type=source_type,
            source_id=source_id,
            raw_value=raw_value,
            score_delta=score_delta,
            max_score_snapshot=criterion.max_score,
            note=note,
            metadata_json=metadata_dump(event_metadata),
        )
        self.db.add(event)
        self.db.flush()
        summary.created_score_events += 1
        self._create_legacy_evidence(
            cycle=cycle,
            member=member,
            criterion=criterion,
            event=event,
            source_type=source_type,
            source_id=source_id,
            summary=summary,
            metadata=event_metadata,
        )
        return event

    def _create_legacy_evidence(
        self,
        *,
        cycle: EvaluationCycle,
        member: Member,
        criterion: EvaluationCriterion,
        event: EvaluationScoreEvent,
        source_type: str,
        source_id: str,
        summary: MigrationSummary,
        metadata: dict[str, Any],
    ) -> None:
        title = f"Legacy migration summary {source_type}:{source_id}"
        existing = self.db.scalar(
            select(EvaluationEvidence).where(
                EvaluationEvidence.cycle_id == cycle.id,
                EvaluationEvidence.member_id == member.id,
                EvaluationEvidence.score_event_id == event.id,
                EvaluationEvidence.evidence_type == EVIDENCE_TYPE_LEGACY_SUMMARY,
                EvaluationEvidence.title == title,
            )
        )
        if existing:
            return
        self.db.add(
            EvaluationEvidence(
                cycle_id=cycle.id,
                member_id=member.id,
                criterion_id=criterion.id,
                score_event_id=event.id,
                evidence_type=EVIDENCE_TYPE_LEGACY_SUMMARY,
                title=title,
                description="Placeholder evidence created from legacy migration.",
                status=EVIDENCE_STATUS_PENDING,
                metadata_json=metadata_dump({**metadata, "unverified": True}),
            )
        )
        summary.created_evidence += 1

    def _create_discipline_case(
        self,
        *,
        cycle: EvaluationCycle,
        member: Member,
        record: DisciplineRecord,
        mapping: dict[str, Any],
        summary: MigrationSummary,
        dry_run: bool,
    ) -> DisciplineCase | None:
        case_code = f"LEGACY-DR-{record.id}"
        existing = self.db.scalar(
            select(DisciplineCase).where(DisciplineCase.case_code == case_code)
        )
        if existing:
            summary.skipped += 1
            return existing
        if mapping["requiresManualReview"]:
            self._queue_manual_review(
                summary,
                source_type=SOURCE_TYPE_LEGACY_DISCIPLINE_RECORD,
                source_id=record.id,
                member_id=member.id,
                mssv=member.mssv,
                name=member.name,
                issue_code="UNKNOWN_DISCIPLINE_LEVEL",
                issue_detail=f"Unknown discipline level: {record.discipline_level}",
                suggested_action="Review and map case type manually",
            )
        if dry_run:
            summary.created_discipline_cases += 1
            return None
        case = DisciplineCase(
            cycle_id=cycle.id,
            member_id=member.id,
            case_code=case_code,
            case_type=mapping["caseType"],
            severity=mapping["severity"],
            title=f"Legacy discipline: {record.discipline_level}",
            description=record.note,
            blocker_code=mapping["blockerCode"],
            source_type=SOURCE_TYPE_LEGACY_DISCIPLINE_RECORD,
            source_id=record.id,
            metadata_json=metadata_dump(
                self._migration_metadata(
                    summary,
                    source_table="discipline_records",
                    source_id=record.id,
                    extra={
                        "legacyDisciplineLevel": record.discipline_level,
                        "migrationConfidence": mapping["confidence"],
                        "requiresManualReview": mapping["requiresManualReview"],
                    },
                )
            ),
        )
        self.db.add(case)
        summary.created_discipline_cases += 1
        return case

    def _load_cycle(self, cycle_id: str) -> EvaluationCycle:
        cycle = self.db.get(EvaluationCycle, cycle_id)
        if not cycle:
            raise EvaluationNotFoundError(f"Evaluation cycle not found: {cycle_id}")
        if cycle.status not in CYCLE_MUTABLE_STATUSES:
            raise EvaluationCycleLockedError(
                f"Cannot migrate into cycle in status {cycle.status}: {cycle_id}"
            )
        return cycle

    def _get_criterion(
        self,
        code: str,
        *,
        summary: MigrationSummary,
        required: bool,
    ) -> EvaluationCriterion | None:
        criterion = self.db.scalar(
            select(EvaluationCriterion).where(
                EvaluationCriterion.code == code,
                EvaluationCriterion.is_active.is_(True),
            )
        )
        if criterion:
            return criterion
        if required:
            raise EvaluationMissingCriteriaError(f"Active criterion not found: {code}")
        self._warn(
            summary,
            "MISSING_CRITERIA_MAPPING",
            f"Active criterion not found: {code}",
            criterionCode=code,
        )
        return None

    def _resolve_record_member(self, record: DisciplineRecord) -> Member | None:
        if record.member_id:
            member = self.db.get(Member, record.member_id)
            if member:
                return member
        return self.db.scalar(select(Member).where(Member.mssv == record.mssv))

    def _find_unmatched_discipline_records(self) -> list[dict[str, Any]]:
        rows = self.db.scalars(select(DisciplineRecord)).all()
        unmatched = []
        for record in rows:
            if self._resolve_record_member(record):
                continue
            unmatched.append(
                {
                    "id": record.id,
                    "memberId": record.member_id,
                    "mssv": record.mssv,
                    "name": record.name,
                }
            )
        return unmatched

    def _migration_metadata(
        self,
        summary: MigrationSummary,
        *,
        source_table: str | None,
        source_id: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "migrationBatchId": summary.migration_batch_id,
            "sourceModule": MIGRATION_SOURCE_MODULE_DISCIPLINE_LEGACY,
            "sourceTable": source_table,
            "sourceId": source_id,
            "migrationMode": summary.mode,
            "migrationVersion": MIGRATION_VERSION_PHASE5,
            **(extra or {}),
        }

    def _queue_manual_review(
        self,
        summary: MigrationSummary,
        *,
        source_type: str,
        source_id: str,
        member_id: str | None,
        mssv: str | None,
        name: str | None,
        issue_code: str,
        issue_detail: str,
        suggested_action: str,
    ) -> None:
        summary.manual_review_queue.append(
            {
                "sourceType": source_type,
                "sourceId": source_id,
                "memberId": member_id,
                "mssv": mssv,
                "name": name,
                "issueCode": issue_code,
                "issueDetail": issue_detail,
                "suggestedAction": suggested_action,
            }
        )

    def _warn(
        self,
        summary: MigrationSummary,
        code: str,
        message: str,
        **details,
    ) -> None:
        summary.warnings.append({"code": code, "message": message, "details": details})

    def _audit_batch(self, action: str, summary: MigrationSummary) -> None:
        create_audit_log(
            db=self.db,
            action=action,
            resource_type="evaluation_migration",
            resource_id=summary.migration_batch_id or "dry-run",
            after_snapshot=summary.as_dict(),
        )

    def _count(self, model) -> int:
        return self.db.scalar(select(func.count()).select_from(model)) or 0

    def _count_where(self, model, *conditions) -> int:
        return self.db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    def _count_distinct(self, column) -> int:
        return self.db.scalar(select(func.count(func.distinct(column)))) or 0

    def _distribution(self, column) -> dict[str, int]:
        rows = self.db.execute(select(column, func.count()).group_by(column)).all()
        return {str(key if key is not None else "NULL"): value for key, value in rows}

    def _numeric_stats(self, column) -> dict[str, float | None]:
        row = self.db.execute(
            select(func.min(column), func.max(column), func.avg(column))
        ).one()
        return {
            "min": float(row[0]) if row[0] is not None else None,
            "max": float(row[1]) if row[1] is not None else None,
            "avg": round(float(row[2]), 2) if row[2] is not None else None,
        }

    def _date_range(self, column) -> dict[str, Any]:
        row = self.db.execute(select(func.min(column), func.max(column))).one()
        return {"min": row[0], "max": row[1]}

    def _limit(self, stmt, batch_size: int | None):
        return stmt.limit(batch_size) if batch_size else stmt
