import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.evaluation_constants import (
    CYCLE_MUTABLE_STATUSES,
    EVENT_TYPE_PENALTY,
)
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import (
    EvaluationAppeal,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationEvidence,
    EvaluationScoreEvent,
    Member,
    MemberCycleRole,
    MemberEvaluation,
    MemberEvaluationBreakdown,
    User,
)
from app.schemas_evaluation import (
    EvaluationAppealCancelRequest,
    EvaluationAppealCreate,
    EvaluationAppealEvidenceRequest,
    EvaluationAppealResolveRequest,
    EvaluationApproveCycleRequest,
    EvaluationComputeRequest,
    EvaluationCriteriaCreate,
    EvaluationCriteriaSeedRequest,
    EvaluationCriteriaStatusUpdate,
    EvaluationCriteriaUpdate,
    EvaluationCycleCreate,
    EvaluationCycleUpdate,
    EvaluationEvidenceCreate,
    EvaluationEvidenceReviewRequest,
    EvaluationOpenReviewRequest,
    EvaluationReopenCorrectionRequest,
    EvaluationScoreEventCreate,
    EvaluationScoreEventBulkCreate,
    EvaluationScoreEventVoidRequest,
    MemberCycleRoleCreate,
    MemberCycleRoleBulkCreate,
    MemberCycleRoleUpdate,
)
from app.services.evaluation_appeal import EvaluationAppealService
from app.services.evaluation_approval import EvaluationApprovalService
from app.services.evaluation_calculator import EvaluationCalculatorService
from app.services.evaluation_criteria_seed import (
    DEFAULT_CRITERIA_EFFECTIVE_FROM,
    EvaluationCriteriaSeedService,
)
from app.services.evaluation_errors import (
    EvaluationAppealAlreadyResolvedError,
    EvaluationAppealNotFoundError,
    EvaluationCorrectionNotAllowedError,
    EvaluationCycleAlreadyApprovedError,
    EvaluationCycleLockedError,
    EvaluationError,
    EvaluationEvidenceError,
    EvaluationInvalidStatusTransitionError,
    EvaluationMissingCriteriaError,
    EvaluationNotFoundError,
    EvaluationNotReadyForApprovalError,
    EvaluationOpenAppealsExistError,
    EvaluationReviewWindowClosedError,
    EvaluationWeightError,
)
from app.services.evaluation_review import EvaluationReviewService
from app.services.evaluation_sync import EvaluationSyncService
from app.utils import sanitize_pagination

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

EVALUATION_ADMIN_ROLES = {"bcn"}
EVALUATION_OPERATOR_ROLES = {"bcn", "bvh_discipline", "bvh_hr"}
EVALUATION_CRITERIA_ROLES = {"bcn", "bvh_discipline"}
EVALUATION_RECORDER_ROLES = {"bcn", "bvh_discipline", "bvh_hr", "bcm"}
EVALUATION_MANAGER_ROLES = {"bcn", "bvh_discipline", "bvh_hr"}
EVALUATION_VOID_ROLES = {"bcn", "bvh_discipline"}
SENSITIVE_METADATA_KEY_PARTS = (
    "apikey",
    "authorization",
    "credential",
    "internalurl",
    "password",
    "secret",
    "signedurl",
    "token",
)

EVALUATION_ERROR_STATUS_MAP = {
    EvaluationCycleLockedError.code: status.HTTP_409_CONFLICT,
    EvaluationInvalidStatusTransitionError.code: status.HTTP_409_CONFLICT,
    EvaluationReviewWindowClosedError.code: status.HTTP_409_CONFLICT,
    EvaluationAppealNotFoundError.code: status.HTTP_404_NOT_FOUND,
    EvaluationAppealAlreadyResolvedError.code: status.HTTP_409_CONFLICT,
    EvaluationNotReadyForApprovalError.code: status.HTTP_422_UNPROCESSABLE_ENTITY,
    EvaluationOpenAppealsExistError.code: status.HTTP_422_UNPROCESSABLE_ENTITY,
    EvaluationCycleAlreadyApprovedError.code: status.HTTP_409_CONFLICT,
    EvaluationCorrectionNotAllowedError.code: status.HTTP_409_CONFLICT,
    EvaluationMissingCriteriaError.code: status.HTTP_422_UNPROCESSABLE_ENTITY,
    EvaluationEvidenceError.code: status.HTTP_422_UNPROCESSABLE_ENTITY,
    EvaluationWeightError.code: status.HTTP_422_UNPROCESSABLE_ENTITY,
    EvaluationNotFoundError.code: status.HTTP_404_NOT_FOUND,
}


def _raise_evaluation_http_error(exc: EvaluationError) -> None:
    detail = {"code": exc.code, "message": str(exc)}
    if exc.details:
        detail["details"] = exc.details
    raise HTTPException(
        status_code=EVALUATION_ERROR_STATUS_MAP.get(
            exc.code, status.HTTP_400_BAD_REQUEST
        ),
        detail=detail,
    )


def _require_roles(current_user: User, roles: set[str]) -> None:
    if not current_user.has_any_roles(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Permission denied"},
        )


def _require_manager(current_user: User) -> None:
    _require_roles(current_user, EVALUATION_MANAGER_ROLES)


def _is_manager(current_user: User) -> bool:
    return current_user.has_any_roles(EVALUATION_MANAGER_ROLES)


def _is_recorder(current_user: User) -> bool:
    return current_user.has_any_roles(EVALUATION_RECORDER_ROLES)


def _get_cycle_or_404(db: Session, cycle_id: str) -> EvaluationCycle:
    cycle = db.get(EvaluationCycle, cycle_id)
    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Evaluation cycle not found"},
        )
    return cycle


def _ensure_cycle_not_locked(cycle: EvaluationCycle) -> None:
    if cycle.status not in CYCLE_MUTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EVALUATION_CYCLE_LOCKED",
                "message": f"Evaluation cycle is not writable in status {cycle.status}",
            },
        )


def _get_member_or_404(db: Session, member_id: str) -> Member:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Member not found"},
        )
    return member


def _is_current_user_linked_to_member(current_user: User, member: Member) -> bool:
    if current_user.username and member.mssv and current_user.username == member.mssv:
        return True
    if current_user.email and member.email:
        return current_user.email.lower() == member.email.lower()
    return False


def _can_access_member(current_user: User, member: Member) -> bool:
    if _is_manager(current_user):
        return True
    if current_user.has_role("bcm"):
        return True
    return _is_current_user_linked_to_member(current_user, member)


def _ensure_can_access_member(current_user: User, member: Member) -> None:
    if not _can_access_member(current_user, member):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot access this member"},
        )


def _metadata_dump(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _metadata_load(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _is_sensitive_metadata_key(key: Any) -> bool:
    normalized = str(key).replace("-", "_").replace(" ", "_").lower()
    compact = normalized.replace("_", "")
    return any(part in compact for part in SENSITIVE_METADATA_KEY_PARTS)


def _sanitize_public_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_public_metadata(item)
            for key, item in value.items()
            if not _is_sensitive_metadata_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_public_metadata(item) for item in value]
    return value


def _public_metadata_load(value: str | None) -> Any:
    return _sanitize_public_metadata(_metadata_load(value))


def _page_rows(db: Session, stmt, page: int, page_size: int) -> tuple[list, dict]:
    page, page_size = sanitize_pagination(page, page_size)
    rows = db.scalars(stmt).all()
    start = (page - 1) * page_size
    return rows[start : start + page_size], {
        "page": page,
        "pageSize": page_size,
        "total": len(rows),
    }


def _cycle_out(cycle: EvaluationCycle) -> dict:
    return {
        "id": cycle.id,
        "code": cycle.code,
        "name": cycle.name,
        "type": cycle.type,
        "startDate": cycle.start_date,
        "endDate": cycle.end_date,
        "status": cycle.status,
        "description": cycle.description,
        "createdByUserId": cycle.created_by_user_id,
        "approvedByUserId": cycle.approved_by_user_id,
        "approvedAt": cycle.approved_at,
        "lockedAt": cycle.locked_at,
        "metadata": _metadata_load(cycle.metadata_json),
        "createdAt": cycle.created_at,
        "updatedAt": cycle.updated_at,
    }


def _criterion_out(criterion: EvaluationCriterion) -> dict:
    return {
        "id": criterion.id,
        "code": criterion.code,
        "name": criterion.name,
        "component": criterion.component,
        "unitScope": criterion.unit_scope,
        "unitCode": criterion.unit_code,
        "maxScore": criterion.max_score,
        "scoreMethod": criterion.score_method,
        "requiresEvidence": criterion.requires_evidence,
        "isActive": criterion.is_active,
        "sortOrder": criterion.sort_order,
        "effectiveFrom": criterion.effective_from,
        "effectiveTo": criterion.effective_to,
        "description": criterion.description,
        "metadata": _metadata_load(criterion.metadata_json),
        "createdAt": criterion.created_at,
        "updatedAt": criterion.updated_at,
    }


def _role_out(role: MemberCycleRole) -> dict:
    return {
        "id": role.id,
        "cycleId": role.cycle_id,
        "memberId": role.member_id,
        "unitCode": role.unit_code,
        "roleType": role.role_type,
        "roleTitle": role.role_title,
        "participationWeight": role.participation_weight,
        "isPrimary": role.is_primary,
        "assignedByUserId": role.assigned_by_user_id,
        "approvedByUserId": role.approved_by_user_id,
        "approvedAt": role.approved_at,
        "note": role.note,
        "metadata": _metadata_load(role.metadata_json),
        "createdAt": role.created_at,
        "updatedAt": role.updated_at,
    }


def _score_event_out(event: EvaluationScoreEvent) -> dict:
    return {
        "id": event.id,
        "cycleId": event.cycle_id,
        "memberId": event.member_id,
        "criterionId": event.criterion_id,
        "criterionCode": event.criterion_code,
        "component": event.component,
        "unitCode": event.unit_code,
        "eventType": event.event_type,
        "sourceType": event.source_type,
        "sourceId": event.source_id,
        "rawValue": event.raw_value,
        "scoreDelta": event.score_delta,
        "maxScoreSnapshot": event.max_score_snapshot,
        "weight": event.weight,
        "note": event.note,
        "recordedByUserId": event.recorded_by_user_id,
        "recordedAt": event.recorded_at,
        "isVoid": event.is_void,
        "voidReason": event.void_reason,
        "metadata": _metadata_load(event.metadata_json),
        "createdAt": event.created_at,
        "updatedAt": event.updated_at,
    }


def _evidence_out(evidence: EvaluationEvidence) -> dict:
    return {
        "id": evidence.id,
        "cycleId": evidence.cycle_id,
        "memberId": evidence.member_id,
        "criterionId": evidence.criterion_id,
        "scoreEventId": evidence.score_event_id,
        "evidenceType": evidence.evidence_type,
        "title": evidence.title,
        "url": evidence.url,
        "filePath": evidence.file_path,
        "description": evidence.description,
        "capturedAt": evidence.captured_at,
        "submittedByUserId": evidence.submitted_by_user_id,
        "verifiedByUserId": evidence.verified_by_user_id,
        "verifiedAt": evidence.verified_at,
        "status": evidence.status,
        "metadata": _public_metadata_load(evidence.metadata_json),
        "createdAt": evidence.created_at,
        "updatedAt": evidence.updated_at,
    }


def _member_evaluation_out(row: MemberEvaluation) -> dict:
    return {
        "id": row.id,
        "cycleId": row.cycle_id,
        "memberId": row.member_id,
        "componentIScore": row.component_i_score,
        "componentIIScore": row.component_ii_score,
        "componentIIiAScore": row.component_iii_a_score,
        "componentIIiBScore": row.component_iii_b_score,
        "totalScore": row.total_score,
        "preliminaryClassification": row.preliminary_classification,
        "finalClassification": row.final_classification,
        "attendanceRate": row.attendance_rate,
        "blockers": _metadata_load(row.blockers_json) or [],
        "calculationVersion": row.calculation_version,
        "computedAt": row.computed_at,
        "approvedByUserId": row.approved_by_user_id,
        "approvedAt": row.approved_at,
        "status": row.status,
        "metadata": _metadata_load(row.metadata_json),
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def _breakdown_out(row: MemberEvaluationBreakdown) -> dict:
    return {
        "id": row.id,
        "memberEvaluationId": row.member_evaluation_id,
        "cycleId": row.cycle_id,
        "memberId": row.member_id,
        "criterionId": row.criterion_id,
        "criterionCode": row.criterion_code,
        "component": row.component,
        "unitCode": row.unit_code,
        "rawScore": row.raw_score,
        "finalScore": row.final_score,
        "maxScoreSnapshot": row.max_score_snapshot,
        "capApplied": row.cap_applied,
        "evidenceCount": row.evidence_count,
        "calculationNote": row.calculation_note,
        "metadata": _metadata_load(row.metadata_json),
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def _appeal_out(row: EvaluationAppeal) -> dict:
    return {
        "id": row.id,
        "cycleId": row.cycle_id,
        "memberId": row.member_id,
        "memberEvaluationId": row.member_evaluation_id,
        "criterionId": row.criterion_id,
        "criterionCode": row.criterion_code,
        "appealType": row.appeal_type,
        "content": row.content,
        "requestedScore": row.requested_score,
        "status": row.status,
        "resolvedByUserId": row.resolved_by_user_id,
        "resolvedAt": row.resolved_at,
        "resolutionNote": row.resolution_note,
        "metadata": _metadata_load(row.metadata_json),
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def _find_criterion(
    db: Session,
    *,
    criterion_id: str | None = None,
    criterion_code: str | None = None,
    unit_code: str | None = None,
) -> EvaluationCriterion:
    if criterion_id:
        criterion = db.get(EvaluationCriterion, criterion_id)
        if criterion:
            return criterion

    if criterion_code:
        rows = db.scalars(
            select(EvaluationCriterion).where(
                EvaluationCriterion.code == criterion_code,
                EvaluationCriterion.is_active.is_(True),
            )
        ).all()
        if unit_code is not None:
            for row in rows:
                if row.unit_code == unit_code:
                    return row
        for row in rows:
            if row.unit_code is None:
                return row
        if rows:
            return rows[0]

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "RESOURCE_NOT_FOUND", "message": "Criterion not found"},
    )


def _criterion_duplicate_exists(
    db: Session,
    *,
    code: str,
    unit_code: str | None,
    effective_from,
    exclude_id: str | None = None,
) -> bool:
    stmt = select(EvaluationCriterion.id).where(
        EvaluationCriterion.code == code,
        EvaluationCriterion.effective_from == effective_from,
    )
    if unit_code is None:
        stmt = stmt.where(EvaluationCriterion.unit_code.is_(None))
    else:
        stmt = stmt.where(EvaluationCriterion.unit_code == unit_code)
    if exclude_id:
        stmt = stmt.where(EvaluationCriterion.id != exclude_id)
    return db.scalar(stmt) is not None


def _existing_source_event(
    db: Session,
    *,
    cycle_id: str,
    body: EvaluationScoreEventCreate,
) -> EvaluationScoreEvent | None:
    if not (body.sourceType and body.sourceId):
        return None
    return db.scalar(
        select(EvaluationScoreEvent).where(
            EvaluationScoreEvent.cycle_id == cycle_id,
            EvaluationScoreEvent.member_id == body.memberId,
            EvaluationScoreEvent.criterion_code == body.criterionCode,
            EvaluationScoreEvent.source_type == body.sourceType,
            EvaluationScoreEvent.source_id == body.sourceId,
            EvaluationScoreEvent.event_type == body.eventType,
            EvaluationScoreEvent.is_void.is_(False),
        )
    )


def _ensure_single_primary_role(
    db: Session,
    *,
    cycle_id: str,
    member_id: str,
    role_id: str | None = None,
) -> None:
    stmt = select(MemberCycleRole.id).where(
        MemberCycleRole.cycle_id == cycle_id,
        MemberCycleRole.member_id == member_id,
        MemberCycleRole.is_primary.is_(True),
    )
    if role_id:
        stmt = stmt.where(MemberCycleRole.id != role_id)
    if db.scalar(stmt):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_PRIMARY_ROLE",
                "message": "Member already has a primary role in this cycle",
            },
        )


@router.post("/cycles")
def create_cycle(
    body: EvaluationCycleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    if db.scalar(select(EvaluationCycle.id).where(EvaluationCycle.code == body.code)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_RESOURCE", "message": "Cycle code already exists"},
        )

    cycle = EvaluationCycle(
        code=body.code,
        name=body.name,
        type=body.type,
        start_date=body.startDate,
        end_date=body.endDate,
        description=body.description,
        created_by_user_id=current_user.id,
    )
    db.add(cycle)
    db.flush()
    create_audit_log(
        db=db,
        action="CREATE_EVALUATION_CYCLE",
        resource_type="evaluation_cycle",
        resource_id=cycle.id,
        actor=current_user,
        after_snapshot={"code": cycle.code, "status": cycle.status},
    )
    db.commit()
    db.refresh(cycle)
    return api_response(data=_cycle_out(cycle))


@router.get("/cycles")
def list_cycles(
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    search: str | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    stmt = select(EvaluationCycle).order_by(EvaluationCycle.start_date.desc())
    if status_filter:
        stmt = stmt.where(EvaluationCycle.status == status_filter)
    if type_filter:
        stmt = stmt.where(EvaluationCycle.type == type_filter)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (EvaluationCycle.code.ilike(pattern))
            | (EvaluationCycle.name.ilike(pattern))
        )
    rows, meta = _page_rows(db, stmt, page, pageSize)
    return api_response(data=[_cycle_out(row) for row in rows], meta=meta)


@router.get("/cycles/{cycle_id}")
def get_cycle(
    cycle_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    return api_response(data=_cycle_out(_get_cycle_or_404(db, cycle_id)))


@router.patch("/cycles/{cycle_id}")
def update_cycle(
    cycle_id: str,
    body: EvaluationCycleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    cycle = _get_cycle_or_404(db, cycle_id)
    _ensure_cycle_not_locked(cycle)

    payload = body.model_dump(exclude_unset=True)
    start_date = payload.get("startDate", cycle.start_date)
    end_date = payload.get("endDate", cycle.end_date)
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DATE_RANGE", "message": "startDate must be <= endDate"},
        )

    mapping = {
        "startDate": "start_date",
        "endDate": "end_date",
    }
    for key, value in payload.items():
        setattr(cycle, mapping.get(key, key), value)

    create_audit_log(
        db=db,
        action="UPDATE_EVALUATION_CYCLE",
        resource_type="evaluation_cycle",
        resource_id=cycle.id,
        actor=current_user,
        after_snapshot={"status": cycle.status},
    )
    db.commit()
    db.refresh(cycle)
    return api_response(data=_cycle_out(cycle))


@router.post("/cycles/{cycle_id}/submit-review")
def submit_cycle_review(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    try:
        result = EvaluationReviewService(db).open_member_review(
            cycle_id,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(result["cycle"])
    return api_response(
        data=_cycle_out(result["cycle"]),
        meta={
            "reviewDeadline": result["reviewDeadline"],
            "updatedMembers": result["updatedMembers"],
        },
    )


@router.post("/cycles/{cycle_id}/review/open")
def open_member_review(
    cycle_id: str,
    body: EvaluationOpenReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    try:
        result = EvaluationReviewService(db).open_member_review(
            cycle_id,
            actor_user_id=current_user.id,
            review_deadline=body.reviewDeadline,
            note=body.note,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(result["cycle"])
    return api_response(
        data=_cycle_out(result["cycle"]),
        meta={
            "reviewDeadline": result["reviewDeadline"],
            "updatedMembers": result["updatedMembers"],
        },
    )


@router.post("/cycles/{cycle_id}/review/close")
def close_member_review(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    try:
        result = EvaluationReviewService(db).close_member_review(
            cycle_id,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(result["cycle"])
    return api_response(
        data=_cycle_out(result["cycle"]),
        meta={
            "openAppeals": result["openAppeals"],
            "nextStatus": result["nextStatus"],
        },
    )


@router.get("/cycles/{cycle_id}/review/summary")
def get_review_summary(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_manager(current_user)
    try:
        result = EvaluationReviewService(db).get_review_summary(cycle_id)
    except EvaluationError as exc:
        _raise_evaluation_http_error(exc)
    return api_response(data=result)


@router.post("/cycles/{cycle_id}/ready-for-approval")
def mark_cycle_ready_for_approval(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    try:
        result = EvaluationApprovalService(db).mark_ready_for_approval(
            cycle_id,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(result["cycle"])
    return api_response(data=_cycle_out(result["cycle"]), meta=result["details"])


@router.post("/cycles/{cycle_id}/approve")
def approve_cycle(
    cycle_id: str,
    body: EvaluationApproveCycleRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_ADMIN_ROLES)
    body = body or EvaluationApproveCycleRequest()
    try:
        result = EvaluationApprovalService(db).approve_cycle(
            cycle_id,
            actor_user_id=current_user.id,
            approval_note=body.approvalNote,
            lock_after_approve=body.lockAfterApprove,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(result["cycle"])
    return api_response(
        data=_cycle_out(result["cycle"]),
        meta={"approvedMembers": result["approvedMembers"]},
    )


@router.post("/cycles/{cycle_id}/lock")
def lock_cycle(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_ADMIN_ROLES)
    try:
        result = EvaluationApprovalService(db).lock_cycle(
            cycle_id,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(result["cycle"])
    return api_response(
        data=_cycle_out(result["cycle"]),
        meta={"lockedMembers": result["lockedMembers"]},
    )


@router.post("/cycles/{cycle_id}/reopen-correction")
def reopen_cycle_correction(
    cycle_id: str,
    body: EvaluationReopenCorrectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_ADMIN_ROLES)
    try:
        cycle = EvaluationApprovalService(db).reopen_approved_cycle_for_correction(
            cycle_id,
            body.reason,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(cycle)
    return api_response(data=_cycle_out(cycle))


@router.post("/cycles/{cycle_id}/cancel")
def cancel_cycle(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_ADMIN_ROLES)
    cycle = _get_cycle_or_404(db, cycle_id)
    _ensure_cycle_not_locked(cycle)
    cycle.status = "CANCELLED"
    create_audit_log(
        db=db,
        action="CANCEL_EVALUATION_CYCLE",
        resource_type="evaluation_cycle",
        resource_id=cycle.id,
        actor=current_user,
    )
    db.commit()
    db.refresh(cycle)
    return api_response(data=_cycle_out(cycle))


@router.post("/criteria/seed")
def seed_criteria(
    body: EvaluationCriteriaSeedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_CRITERIA_ROLES)
    effective_from = body.effectiveFrom or DEFAULT_CRITERIA_EFFECTIVE_FROM
    result = EvaluationCriteriaSeedService(db).seed_default_criteria_2026(
        effective_from=effective_from,
        actor_user_id=current_user.id,
    )
    db.commit()
    return api_response(data={"version": body.version, **result})


@router.get("/criteria")
def list_criteria(
    component: str | None = None,
    unitCode: str | None = None,
    isActive: bool | None = None,
    search: str | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=50),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    stmt = select(EvaluationCriterion).order_by(
        EvaluationCriterion.sort_order, EvaluationCriterion.code
    )
    if component:
        stmt = stmt.where(EvaluationCriterion.component == component)
    if unitCode:
        stmt = stmt.where(EvaluationCriterion.unit_code == unitCode)
    if isActive is not None:
        stmt = stmt.where(EvaluationCriterion.is_active.is_(isActive))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (EvaluationCriterion.code.ilike(pattern))
            | (EvaluationCriterion.name.ilike(pattern))
        )
    rows, meta = _page_rows(db, stmt, page, pageSize)
    return api_response(data=[_criterion_out(row) for row in rows], meta=meta)


@router.get("/criteria/{criterion_id}")
def get_criterion(
    criterion_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    criterion = db.get(EvaluationCriterion, criterion_id)
    if not criterion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Criterion not found"},
        )
    return api_response(data=_criterion_out(criterion))


@router.post("/criteria")
def create_criterion(
    body: EvaluationCriteriaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_CRITERIA_ROLES)
    if _criterion_duplicate_exists(
        db,
        code=body.code,
        unit_code=body.unitCode,
        effective_from=body.effectiveFrom,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_RESOURCE", "message": "Criterion already exists"},
        )

    criterion = EvaluationCriterion(
        code=body.code,
        name=body.name,
        component=body.component,
        unit_scope=body.unitScope,
        unit_code=body.unitCode,
        max_score=body.maxScore,
        score_method=body.scoreMethod,
        requires_evidence=body.requiresEvidence,
        sort_order=body.sortOrder,
        effective_from=body.effectiveFrom,
        effective_to=body.effectiveTo,
        description=body.description,
        metadata_json=_metadata_dump(body.metadata),
    )
    db.add(criterion)
    db.flush()
    create_audit_log(
        db=db,
        action="CREATE_EVALUATION_CRITERION",
        resource_type="evaluation_criterion",
        resource_id=criterion.id,
        actor=current_user,
        after_snapshot={"code": criterion.code},
    )
    db.commit()
    db.refresh(criterion)
    return api_response(data=_criterion_out(criterion))


@router.patch("/criteria/{criterion_id}")
def update_criterion(
    criterion_id: str,
    body: EvaluationCriteriaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_CRITERIA_ROLES)
    criterion = db.get(EvaluationCriterion, criterion_id)
    if not criterion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Criterion not found"},
        )

    payload = body.model_dump(exclude_unset=True)
    next_code = payload.get("code", criterion.code)
    next_unit_code = payload.get("unitCode", criterion.unit_code)
    next_effective_from = payload.get("effectiveFrom", criterion.effective_from)
    if _criterion_duplicate_exists(
        db,
        code=next_code,
        unit_code=next_unit_code,
        effective_from=next_effective_from,
        exclude_id=criterion.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_RESOURCE", "message": "Criterion already exists"},
        )

    mapping = {
        "unitScope": "unit_scope",
        "unitCode": "unit_code",
        "maxScore": "max_score",
        "scoreMethod": "score_method",
        "requiresEvidence": "requires_evidence",
        "isActive": "is_active",
        "sortOrder": "sort_order",
        "effectiveFrom": "effective_from",
        "effectiveTo": "effective_to",
    }
    for key, value in payload.items():
        if key == "metadata":
            criterion.metadata_json = _metadata_dump(value)
        else:
            setattr(criterion, mapping.get(key, key), value)

    create_audit_log(
        db=db,
        action="UPDATE_EVALUATION_CRITERION",
        resource_type="evaluation_criterion",
        resource_id=criterion.id,
        actor=current_user,
    )
    db.commit()
    db.refresh(criterion)
    return api_response(data=_criterion_out(criterion))


@router.patch("/criteria/{criterion_id}/status")
def update_criterion_status(
    criterion_id: str,
    body: EvaluationCriteriaStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_CRITERIA_ROLES)
    criterion = db.get(EvaluationCriterion, criterion_id)
    if not criterion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Criterion not found"},
        )
    criterion.is_active = body.isActive
    db.commit()
    db.refresh(criterion)
    return api_response(data=_criterion_out(criterion))


@router.post("/cycles/{cycle_id}/member-roles/bulk")
def create_member_roles_bulk(
    cycle_id: str,
    body: MemberCycleRoleBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    cycle = _get_cycle_or_404(db, cycle_id)
    _ensure_cycle_not_locked(cycle)
    
    created_count = 0
    updated_count = 0
    
    for role_body in body.roles:
        _get_member_or_404(db, role_body.memberId)
        
        # Determine isPrimary: if this is the only role, make it primary.
        is_primary = role_body.isPrimary
        if is_primary:
            _ensure_single_primary_role(db, cycle_id=cycle_id, member_id=role_body.memberId)
            
        existing_role = db.scalar(
            select(MemberCycleRole).where(
                MemberCycleRole.cycle_id == cycle_id,
                MemberCycleRole.member_id == role_body.memberId,
                MemberCycleRole.unit_code == role_body.unitCode,
                MemberCycleRole.role_type == role_body.roleType
            )
        )
        
        if existing_role:
            existing_role.role_title = role_body.roleTitle
            existing_role.participation_weight = role_body.participationWeight
            if is_primary:
                existing_role.is_primary = True
            if role_body.note is not None:
                existing_role.note = role_body.note
            if role_body.metadata is not None:
                existing_role.metadata_json = _metadata_dump(role_body.metadata)
            updated_count += 1
        else:
            new_role = MemberCycleRole(
                cycle_id=cycle_id,
                member_id=role_body.memberId,
                unit_code=role_body.unitCode,
                role_type=role_body.roleType,
                role_title=role_body.roleTitle,
                participation_weight=role_body.participationWeight,
                is_primary=is_primary,
                note=role_body.note,
                metadata_json=_metadata_dump(role_body.metadata),
            )
            db.add(new_role)
            created_count += 1
            
    db.commit()
    return api_response(data={"createdCount": created_count, "updatedCount": updated_count}, message=f"Đã lưu thành công. Tạo mới: {created_count}, Cập nhật: {updated_count}.")


@router.post("/cycles/{cycle_id}/member-roles")
def create_member_role(
    cycle_id: str,
    body: MemberCycleRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    cycle = _get_cycle_or_404(db, cycle_id)
    _ensure_cycle_not_locked(cycle)
    _get_member_or_404(db, body.memberId)
    if body.isPrimary:
        _ensure_single_primary_role(db, cycle_id=cycle_id, member_id=body.memberId)
    if db.scalar(
        select(MemberCycleRole.id).where(
            MemberCycleRole.cycle_id == cycle_id,
            MemberCycleRole.member_id == body.memberId,
            MemberCycleRole.unit_code == body.unitCode,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_RESOURCE", "message": "Role already exists"},
        )

    role = MemberCycleRole(
        cycle_id=cycle_id,
        member_id=body.memberId,
        unit_code=body.unitCode,
        role_type=body.roleType,
        role_title=body.roleTitle,
        participation_weight=body.participationWeight,
        is_primary=body.isPrimary,
        assigned_by_user_id=current_user.id,
        note=body.note,
        metadata_json=_metadata_dump(body.metadata),
    )
    db.add(role)
    db.flush()
    create_audit_log(
        db=db,
        action="CREATE_MEMBER_CYCLE_ROLE",
        resource_type="member_cycle_role",
        resource_id=role.id,
        actor=current_user,
    )
    db.commit()
    db.refresh(role)
    return api_response(data=_role_out(role))


@router.get("/cycles/{cycle_id}/member-roles")
def list_member_roles(
    cycle_id: str,
    memberId: str | None = None,
    unitCode: str | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    stmt = select(MemberCycleRole).where(MemberCycleRole.cycle_id == cycle_id)
    if memberId:
        stmt = stmt.where(MemberCycleRole.member_id == memberId)
    if unitCode:
        stmt = stmt.where(MemberCycleRole.unit_code == unitCode)
    rows, meta = _page_rows(db, stmt.order_by(MemberCycleRole.unit_code), page, pageSize)
    return api_response(data=[_role_out(row) for row in rows], meta=meta)


@router.get("/cycles/{cycle_id}/members/{member_id}/roles")
def get_member_roles(
    cycle_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    member = _get_member_or_404(db, member_id)
    _ensure_can_access_member(current_user, member)
    rows = db.scalars(
        select(MemberCycleRole).where(
            MemberCycleRole.cycle_id == cycle_id,
            MemberCycleRole.member_id == member_id,
        )
    ).all()
    return api_response(data=[_role_out(row) for row in rows])


@router.patch("/member-roles/{role_id}")
def update_member_role(
    role_id: str,
    body: MemberCycleRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    role = db.get(MemberCycleRole, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Member role not found"},
        )
    cycle = _get_cycle_or_404(db, role.cycle_id)
    _ensure_cycle_not_locked(cycle)
    payload = body.model_dump(exclude_unset=True)
    if payload.get("isPrimary") is True:
        _ensure_single_primary_role(
            db, cycle_id=role.cycle_id, member_id=role.member_id, role_id=role.id
        )
    mapping = {
        "unitCode": "unit_code",
        "roleType": "role_type",
        "roleTitle": "role_title",
        "participationWeight": "participation_weight",
        "isPrimary": "is_primary",
    }
    for key, value in payload.items():
        if key == "metadata":
            role.metadata_json = _metadata_dump(value)
        else:
            setattr(role, mapping.get(key, key), value)
    db.commit()
    db.refresh(role)
    return api_response(data=_role_out(role))


@router.delete("/member-roles/{role_id}")
def delete_member_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, {"bcn", "bvh_hr"})
    role = db.get(MemberCycleRole, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Member role not found"},
        )
    cycle = _get_cycle_or_404(db, role.cycle_id)
    _ensure_cycle_not_locked(cycle)
    db.delete(role)
    db.commit()
    return api_response(data={"deleted": True, "id": role_id})


@router.post("/cycles/{cycle_id}/score-events/bulk")
def create_score_events_bulk(
    cycle_id: str,
    body: EvaluationScoreEventBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_RECORDER_ROLES)
    cycle = _get_cycle_or_404(db, cycle_id)
    _ensure_cycle_not_locked(cycle)
    
    created_count = 0
    for evt_body in body.events:
        _get_member_or_404(db, evt_body.memberId)
        
        if evt_body.sourceType == "SPREADSHEET":
            existing = db.scalar(
                select(EvaluationScoreEvent).where(
                    EvaluationScoreEvent.cycle_id == cycle_id,
                    EvaluationScoreEvent.member_id == evt_body.memberId,
                    EvaluationScoreEvent.criterion_code == evt_body.criterionCode,
                    EvaluationScoreEvent.source_type == "SPREADSHEET",
                    EvaluationScoreEvent.is_void.is_(False)
                )
            )
            if existing:
                if existing.score_delta == evt_body.scoreDelta and existing.note == evt_body.note:
                    continue
                existing.is_void = True
                existing.void_reason = "Overwritten by spreadsheet update"
                existing.voided_at = func.now()
                existing.voided_by_user_id = current_user.id
                db.add(existing)
        else:
            existing_source = _existing_source_event(db, cycle_id=cycle_id, body=evt_body)
            if existing_source:
                continue

        criterion = _find_criterion(
            db,
            criterion_id=evt_body.criterionId,
            criterion_code=evt_body.criterionCode,
            unit_code=evt_body.unitCode,
        )
        score_delta = evt_body.scoreDelta
        if evt_body.eventType == EVENT_TYPE_PENALTY and score_delta > 0:
            score_delta = -score_delta

        event = EvaluationScoreEvent(
            cycle_id=cycle_id,
            member_id=evt_body.memberId,
            criterion_id=criterion.id,
            criterion_code=criterion.code,
            component=criterion.component,
            unit_code=evt_body.unitCode if evt_body.unitCode is not None else criterion.unit_code,
            event_type=evt_body.eventType,
            source_type=evt_body.sourceType,
            source_id=evt_body.sourceId,
            raw_value=evt_body.rawValue,
            score_delta=score_delta,
            max_score_snapshot=criterion.max_score,
            weight=evt_body.weight,
            note=evt_body.note,
            recorded_by_user_id=current_user.id,
            metadata_json=_metadata_dump(evt_body.metadata),
        )
        db.add(event)
        created_count += 1

    db.commit()
    return api_response(data={"createdCount": created_count}, message=f"Đã lưu thành công {created_count} sự kiện điểm.")


@router.post("/cycles/{cycle_id}/score-events")
def create_score_event(
    cycle_id: str,
    body: EvaluationScoreEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_RECORDER_ROLES)
    cycle = _get_cycle_or_404(db, cycle_id)
    _ensure_cycle_not_locked(cycle)
    _get_member_or_404(db, body.memberId)
    existing = _existing_source_event(db, cycle_id=cycle_id, body=body)
    if existing:
        return api_response(data=_score_event_out(existing), meta={"created": False})

    criterion = _find_criterion(
        db,
        criterion_id=body.criterionId,
        criterion_code=body.criterionCode,
        unit_code=body.unitCode,
    )
    score_delta = body.scoreDelta
    if body.eventType == EVENT_TYPE_PENALTY and score_delta > 0:
        score_delta = -score_delta

    event = EvaluationScoreEvent(
        cycle_id=cycle_id,
        member_id=body.memberId,
        criterion_id=criterion.id,
        criterion_code=criterion.code,
        component=criterion.component,
        unit_code=body.unitCode if body.unitCode is not None else criterion.unit_code,
        event_type=body.eventType,
        source_type=body.sourceType,
        source_id=body.sourceId,
        raw_value=body.rawValue,
        score_delta=score_delta,
        max_score_snapshot=criterion.max_score,
        weight=body.weight,
        note=body.note,
        recorded_by_user_id=current_user.id,
        metadata_json=_metadata_dump(body.metadata),
    )
    db.add(event)
    db.flush()
    create_audit_log(
        db=db,
        action="CREATE_EVALUATION_SCORE_EVENT",
        resource_type="evaluation_score_event",
        resource_id=event.id,
        actor=current_user,
        after_snapshot={"criterionCode": event.criterion_code, "scoreDelta": score_delta},
    )
    db.commit()
    db.refresh(event)
    return api_response(data=_score_event_out(event), meta={"created": True})


@router.get("/cycles/{cycle_id}/score-events")
def list_score_events(
    cycle_id: str,
    memberId: str | None = None,
    criterionCode: str | None = None,
    component: str | None = None,
    unitCode: str | None = None,
    eventType: str | None = None,
    sourceType: str | None = None,
    isVoid: bool | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if memberId:
        _ensure_can_access_member(current_user, _get_member_or_404(db, memberId))
    else:
        _require_roles(current_user, EVALUATION_RECORDER_ROLES)

    stmt = select(EvaluationScoreEvent).where(EvaluationScoreEvent.cycle_id == cycle_id)
    if memberId:
        stmt = stmt.where(EvaluationScoreEvent.member_id == memberId)
    if criterionCode:
        stmt = stmt.where(EvaluationScoreEvent.criterion_code == criterionCode)
    if component:
        stmt = stmt.where(EvaluationScoreEvent.component == component)
    if unitCode:
        stmt = stmt.where(EvaluationScoreEvent.unit_code == unitCode)
    if eventType:
        stmt = stmt.where(EvaluationScoreEvent.event_type == eventType)
    if sourceType:
        stmt = stmt.where(EvaluationScoreEvent.source_type == sourceType)
    if isVoid is not None:
        stmt = stmt.where(EvaluationScoreEvent.is_void.is_(isVoid))
    rows, meta = _page_rows(db, stmt.order_by(EvaluationScoreEvent.created_at.desc()), page, pageSize)
    return api_response(data=[_score_event_out(row) for row in rows], meta=meta)


@router.patch("/score-events/{event_id}/void")
def void_score_event(
    event_id: str,
    body: EvaluationScoreEventVoidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_VOID_ROLES)
    event = db.get(EvaluationScoreEvent, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Score event not found"},
        )
    cycle = _get_cycle_or_404(db, event.cycle_id)
    _ensure_cycle_not_locked(cycle)
    event.is_void = True
    event.void_reason = body.reason
    create_audit_log(
        db=db,
        action="VOID_EVALUATION_SCORE_EVENT",
        resource_type="evaluation_score_event",
        resource_id=event.id,
        actor=current_user,
        after_snapshot={"voidReason": body.reason},
    )
    db.commit()
    db.refresh(event)
    return api_response(data=_score_event_out(event))


@router.post("/cycles/{cycle_id}/evidence")
def create_evidence(
    cycle_id: str,
    body: EvaluationEvidenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    cycle = _get_cycle_or_404(db, cycle_id)
    _ensure_cycle_not_locked(cycle)
    member = _get_member_or_404(db, body.memberId)
    if not (_is_recorder(current_user) or _is_current_user_linked_to_member(current_user, member)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot submit evidence for this member"},
        )

    criterion_id = body.criterionId
    score_event_id = body.scoreEventId
    if score_event_id:
        event = db.get(EvaluationScoreEvent, score_event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "Score event not found"},
            )
        if event.cycle_id != cycle_id or event.member_id != body.memberId:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "EVIDENCE_EVENT_MISMATCH", "message": "Evidence does not match score event"},
            )
        criterion_id = event.criterion_id
    elif body.criterionCode:
        criterion_id = _find_criterion(
            db,
            criterion_id=body.criterionId,
            criterion_code=body.criterionCode,
        ).id

    evidence = EvaluationEvidence(
        cycle_id=cycle_id,
        member_id=body.memberId,
        criterion_id=criterion_id,
        score_event_id=score_event_id,
        evidence_type=body.evidenceType,
        title=body.title,
        url=body.url,
        file_path=body.filePath,
        description=body.description,
        captured_at=body.capturedAt,
        submitted_by_user_id=current_user.id,
        metadata_json=_metadata_dump(body.metadata),
    )
    db.add(evidence)
    db.flush()
    create_audit_log(
        db=db,
        action="CREATE_EVALUATION_EVIDENCE",
        resource_type="evaluation_evidence",
        resource_id=evidence.id,
        actor=current_user,
    )
    db.commit()
    db.refresh(evidence)
    return api_response(data=_evidence_out(evidence))


@router.get("/cycles/{cycle_id}/evidence")
def list_evidence(
    cycle_id: str,
    memberId: str | None = None,
    criterionId: str | None = None,
    evidenceType: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1),
    pageSize: int = Query(default=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if memberId:
        _ensure_can_access_member(current_user, _get_member_or_404(db, memberId))
    else:
        _require_roles(current_user, EVALUATION_RECORDER_ROLES)

    stmt = select(EvaluationEvidence).where(EvaluationEvidence.cycle_id == cycle_id)
    if memberId:
        stmt = stmt.where(EvaluationEvidence.member_id == memberId)
    if criterionId:
        stmt = stmt.where(EvaluationEvidence.criterion_id == criterionId)
    if evidenceType:
        stmt = stmt.where(EvaluationEvidence.evidence_type == evidenceType)
    if status_filter:
        stmt = stmt.where(EvaluationEvidence.status == status_filter)
    rows, meta = _page_rows(db, stmt.order_by(EvaluationEvidence.created_at.desc()), page, pageSize)
    return api_response(data=[_evidence_out(row) for row in rows], meta=meta)


def _review_evidence(
    evidence_id: str,
    *,
    next_status: str,
    action: str,
    body: EvaluationEvidenceReviewRequest,
    db: Session,
    current_user: User,
) -> dict:
    _require_roles(current_user, EVALUATION_RECORDER_ROLES)
    evidence = db.get(EvaluationEvidence, evidence_id)
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Evidence not found"},
        )
    cycle = _get_cycle_or_404(db, evidence.cycle_id)
    _ensure_cycle_not_locked(cycle)
    if evidence.submitted_by_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "EVIDENCE_SELF_REVIEW_NOT_ALLOWED",
                "message": "Evidence submitter cannot review their own evidence",
            },
        )
    evidence.status = next_status
    evidence.verified_by_user_id = current_user.id
    evidence.verified_at = datetime.now(UTC)
    create_audit_log(
        db=db,
        action=action,
        resource_type="evaluation_evidence",
        resource_id=evidence.id,
        actor=current_user,
        after_snapshot={"status": next_status, "note": body.note},
    )
    db.commit()
    db.refresh(evidence)
    return api_response(data=_evidence_out(evidence))


@router.patch("/evidence/{evidence_id}/verify")
def verify_evidence(
    evidence_id: str,
    body: EvaluationEvidenceReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return _review_evidence(
        evidence_id,
        next_status="VERIFIED",
        action="VERIFY_EVALUATION_EVIDENCE",
        body=body,
        db=db,
        current_user=current_user,
    )


@router.patch("/evidence/{evidence_id}/reject")
def reject_evidence(
    evidence_id: str,
    body: EvaluationEvidenceReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return _review_evidence(
        evidence_id,
        next_status="REJECTED",
        action="REJECT_EVALUATION_EVIDENCE",
        body=body,
        db=db,
        current_user=current_user,
    )


@router.post("/cycles/{cycle_id}/compute")
def compute_cycle(
    cycle_id: str,
    body: EvaluationComputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    try:
        result = EvaluationCalculatorService(db).compute_cycle(
            cycle_id,
            actor_user_id=current_user.id,
            strict=body.strict,
            evidence_mode=body.evidenceMode,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    return api_response(data=result)


@router.post("/cycles/{cycle_id}/members/{member_id}/compute")
def compute_member(
    cycle_id: str,
    member_id: str,
    body: EvaluationComputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_OPERATOR_ROLES)
    try:
        result = EvaluationCalculatorService(db).compute_member(
            cycle_id,
            member_id,
            actor_user_id=current_user.id,
            strict=body.strict,
            evidence_mode=body.evidenceMode,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    return api_response(data=result)


@router.get("/cycles/{cycle_id}/members")
def list_member_results(
    cycle_id: str,
    classification: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    minScore: float | None = None,
    maxScore: float | None = None,
    unitCode: str | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_manager(current_user)
    stmt = select(MemberEvaluation).where(MemberEvaluation.cycle_id == cycle_id)
    if classification:
        stmt = stmt.where(MemberEvaluation.final_classification == classification)
    if status_filter:
        stmt = stmt.where(MemberEvaluation.status == status_filter)
    if minScore is not None:
        stmt = stmt.where(MemberEvaluation.total_score >= minScore)
    if maxScore is not None:
        stmt = stmt.where(MemberEvaluation.total_score <= maxScore)
    if unitCode:
        member_ids = select(MemberCycleRole.member_id).where(
            MemberCycleRole.cycle_id == cycle_id,
            MemberCycleRole.unit_code == unitCode,
        )
        stmt = stmt.where(MemberEvaluation.member_id.in_(member_ids))
    rows, meta = _page_rows(db, stmt.order_by(MemberEvaluation.total_score.desc()), page, pageSize)
    return api_response(data=[_member_evaluation_out(row) for row in rows], meta=meta)


@router.get("/cycles/{cycle_id}/members/{member_id}")
def get_member_result(
    cycle_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    member = _get_member_or_404(db, member_id)
    _ensure_can_access_member(current_user, member)
    row = db.scalar(
        select(MemberEvaluation).where(
            MemberEvaluation.cycle_id == cycle_id,
            MemberEvaluation.member_id == member_id,
        )
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Member evaluation not found"},
        )
    return api_response(data=_member_evaluation_out(row))


@router.get("/cycles/{cycle_id}/members/{member_id}/breakdowns")
def get_member_breakdowns(
    cycle_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    member = _get_member_or_404(db, member_id)
    _ensure_can_access_member(current_user, member)
    rows = db.scalars(
        select(MemberEvaluationBreakdown)
        .where(
            MemberEvaluationBreakdown.cycle_id == cycle_id,
            MemberEvaluationBreakdown.member_id == member_id,
        )
        .order_by(MemberEvaluationBreakdown.component, MemberEvaluationBreakdown.criterion_code)
    ).all()
    return api_response(data=[_breakdown_out(row) for row in rows])


@router.get("/cycles/{cycle_id}/summary")
def get_cycle_summary(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_manager(current_user)
    total_members = (
        db.scalar(
            select(func.count())
            .select_from(MemberEvaluation)
            .where(MemberEvaluation.cycle_id == cycle_id)
        )
        or 0
    )
    avg_score = (
        db.scalar(
            select(func.avg(MemberEvaluation.total_score)).where(
                MemberEvaluation.cycle_id == cycle_id
            )
        )
        or 0.0
    )
    distribution_rows = db.execute(
        select(MemberEvaluation.final_classification, func.count())
        .where(MemberEvaluation.cycle_id == cycle_id)
        .group_by(MemberEvaluation.final_classification)
    ).all()
    return api_response(
        data={
            "cycleId": cycle_id,
            "totalMembers": total_members,
            "averageScore": round(float(avg_score), 2),
            "classificationDistribution": {
                key or "UNCLASSIFIED": value for key, value in distribution_rows
            },
        }
    )


@router.post("/cycles/{cycle_id}/sync/attendance/{meeting_id}")
def sync_attendance(
    cycle_id: str,
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_VOID_ROLES)
    try:
        result = EvaluationSyncService(db).sync_attendance_to_score_events(
            cycle_id,
            meeting_id,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    return api_response(data=result)


@router.post("/cycles/{cycle_id}/sync/competition/{competition_id}")
def sync_competition(
    cycle_id: str,
    competition_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, {"bcn", "bvh_discipline", "bcm"})
    try:
        result = EvaluationSyncService(db).sync_competition_to_score_events(
            cycle_id,
            competition_id,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    return api_response(data=result)


@router.post("/cycles/{cycle_id}/appeals")
def create_appeal(
    cycle_id: str,
    body: EvaluationAppealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    member = _get_member_or_404(db, body.memberId)
    if not (_is_manager(current_user) or _is_current_user_linked_to_member(current_user, member)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot create appeal for this member"},
        )
    try:
        appeal = EvaluationAppealService(db).create_appeal(
            cycle_id,
            body.model_dump(),
            actor_user_id=current_user.id,
            allow_late=_is_manager(current_user),
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(appeal)
    return api_response(data=_appeal_out(appeal))


@router.get("/cycles/{cycle_id}/appeals")
def list_appeals(
    cycle_id: str,
    memberId: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1),
    pageSize: int = Query(default=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if memberId:
        _ensure_can_access_member(current_user, _get_member_or_404(db, memberId))
    else:
        _require_manager(current_user)
    stmt = select(EvaluationAppeal).where(EvaluationAppeal.cycle_id == cycle_id)
    if memberId:
        stmt = stmt.where(EvaluationAppeal.member_id == memberId)
    if status_filter:
        stmt = stmt.where(EvaluationAppeal.status == status_filter)
    rows, meta = _page_rows(db, stmt.order_by(EvaluationAppeal.created_at.desc()), page, pageSize)
    return api_response(data=[_appeal_out(row) for row in rows], meta=meta)


@router.get("/appeals/{appeal_id}")
def get_appeal(
    appeal_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    appeal = db.get(EvaluationAppeal, appeal_id)
    if not appeal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Appeal not found"},
        )
    _ensure_can_access_member(current_user, _get_member_or_404(db, appeal.member_id))
    return api_response(data=_appeal_out(appeal))


@router.post("/appeals/{appeal_id}/start-review")
def start_appeal_review(
    appeal_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_RECORDER_ROLES)
    try:
        appeal = EvaluationAppealService(db).start_review(
            appeal_id,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(appeal)
    return api_response(data=_appeal_out(appeal))


@router.post("/appeals/{appeal_id}/request-evidence")
def request_appeal_evidence(
    appeal_id: str,
    body: EvaluationAppealEvidenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_RECORDER_ROLES)
    try:
        appeal = EvaluationAppealService(db).request_more_evidence(
            appeal_id,
            body.note,
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(appeal)
    return api_response(data=_appeal_out(appeal))


@router.post("/appeals/{appeal_id}/resolve")
def resolve_appeal(
    appeal_id: str,
    body: EvaluationAppealResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, EVALUATION_RECORDER_ROLES)
    try:
        result = EvaluationAppealService(db).resolve_appeal(
            appeal_id,
            body.model_dump(),
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(result["appeal"])
    if result["adjustmentEvent"]:
        db.refresh(result["adjustmentEvent"])
    return api_response(
        data=_appeal_out(result["appeal"]),
        meta={
            "adjustmentEvent": (
                _score_event_out(result["adjustmentEvent"])
                if result["adjustmentEvent"]
                else None
            ),
            "recomputed": result["recomputed"],
        },
    )


@router.post("/appeals/{appeal_id}/cancel")
def cancel_appeal(
    appeal_id: str,
    body: EvaluationAppealCancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    appeal = db.get(EvaluationAppeal, appeal_id)
    if not appeal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Appeal not found"},
        )
    if not _is_manager(current_user):
        _ensure_can_access_member(current_user, _get_member_or_404(db, appeal.member_id))
    try:
        appeal = EvaluationAppealService(db).cancel_appeal(
            appeal_id,
            (body.reason if body else None),
            actor_user_id=current_user.id,
        )
    except EvaluationError as exc:
        db.rollback()
        _raise_evaluation_http_error(exc)
    db.commit()
    db.refresh(appeal)
    return api_response(data=_appeal_out(appeal))
