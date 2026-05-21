from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import Member, MemberCycleRole, User
from app.services.evaluation_errors import EvaluationNotFoundError
from app.services.evaluation_export import EvaluationExportService
from app.services.evaluation_report import EvaluationReportService

router = APIRouter(prefix="/evaluations/reports", tags=["evaluation-reports"])

REPORT_MANAGER_ROLES = {"bcn", "bvh_discipline", "bvh_hr"}
RISK_REPORT_ROLES = {"bcn", "bvh_discipline"}


def _raise_report_not_found(exc: EvaluationNotFoundError) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "EVALUATION_REPORT_NOT_FOUND", "message": str(exc)},
    ) from exc


def _require_roles(current_user: User, roles: set[str]) -> None:
    if not current_user.has_any_roles(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "EVALUATION_REPORT_FORBIDDEN", "message": "Permission denied"},
        )


def _is_report_manager(current_user: User) -> bool:
    return current_user.has_any_roles(REPORT_MANAGER_ROLES)


def _linked_member(db: Session, current_user: User) -> Member | None:
    if current_user.username:
        member = db.scalar(select(Member).where(Member.mssv == current_user.username))
        if member:
            return member
    if current_user.email:
        return db.scalar(select(Member).where(Member.email == current_user.email))
    return None


def _is_own_member(db: Session, current_user: User, member_id: str) -> bool:
    member = _linked_member(db, current_user)
    return bool(member and member.id == member_id)


def _user_unit_codes(db: Session, current_user: User, cycle_id: str) -> set[str]:
    member = _linked_member(db, current_user)
    if not member:
        return set()
    roles = db.scalars(
        select(MemberCycleRole).where(
            MemberCycleRole.cycle_id == cycle_id,
            MemberCycleRole.member_id == member.id,
        )
    ).all()
    unit_codes = {role.unit_code for role in roles if role.unit_code}
    if member.ban:
        unit_codes.add(member.ban)
    return unit_codes


def _ensure_member_report_access(
    db: Session, current_user: User, cycle_id: str, member_id: str
) -> None:
    if _is_report_manager(current_user) or _is_own_member(db, current_user, member_id):
        return
    if current_user.has_role("bcm"):
        target_roles = db.scalars(
            select(MemberCycleRole).where(
                MemberCycleRole.cycle_id == cycle_id,
                MemberCycleRole.member_id == member_id,
            )
        ).all()
        target_units = {role.unit_code for role in target_roles if role.unit_code}
        target = db.get(Member, member_id)
        if target and target.ban:
            target_units.add(target.ban)
        if target_units.intersection(_user_unit_codes(db, current_user, cycle_id)):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "EVALUATION_REPORT_FORBIDDEN", "message": "Cannot access report"},
    )


def _ensure_unit_report_access(
    db: Session, current_user: User, cycle_id: str, unit_code: str
) -> None:
    if _is_report_manager(current_user):
        return
    if current_user.has_role("bcm") and unit_code in _user_unit_codes(
        db, current_user, cycle_id
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "EVALUATION_REPORT_FORBIDDEN",
            "message": "Cannot access unit report",
        },
    )


def _filters(
    unitCode: str | None = None,
    classification: str | None = None,
    status_filter: str | None = None,
    minScore: float | None = None,
    maxScore: float | None = None,
    hasBlocker: bool | None = None,
    hasAppeal: bool | None = None,
    hasDisciplineCase: bool | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    return {
        "unitCode": unitCode,
        "classification": classification,
        "status": status_filter,
        "minScore": minScore,
        "maxScore": maxScore,
        "hasBlocker": hasBlocker,
        "hasAppeal": hasAppeal,
        "hasDisciplineCase": hasDisciplineCase,
        "search": search,
    }


@router.get("/cycles/{cycle_id}/dashboard")
def get_cycle_dashboard(
    cycle_id: str,
    unitCode: str | None = None,
    classification: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    minScore: float | None = None,
    maxScore: float | None = None,
    hasBlocker: bool | None = None,
    hasAppeal: bool | None = None,
    hasDisciplineCase: bool | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        data = EvaluationReportService(db).get_cycle_dashboard(
            cycle_id,
            _filters(
                unitCode,
                classification,
                status_filter,
                minScore,
                maxScore,
                hasBlocker,
                hasAppeal,
                hasDisciplineCase,
                search,
            ),
        )
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/summary")
def get_cycle_summary(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        data = EvaluationReportService(db).get_cycle_summary(cycle_id)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/classification-distribution")
def get_classification_distribution(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        data = EvaluationReportService(db).get_classification_distribution(cycle_id)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/component-averages")
def get_component_averages(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        data = EvaluationReportService(db).get_component_averages(cycle_id)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/risk-summary")
def get_risk_summary(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, RISK_REPORT_ROLES)
    try:
        data = EvaluationReportService(db).get_risk_report(cycle_id)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/appeals")
def get_appeal_report(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        data = EvaluationReportService(db).get_appeal_report(cycle_id)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/members/{member_id}")
def get_member_report(
    cycle_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_member_report_access(db, current_user, cycle_id, member_id)
    try:
        data = EvaluationReportService(db).get_member_report(cycle_id, member_id)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/units")
def get_units_report(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        data = EvaluationReportService(db).get_units_report(cycle_id)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/units/{unit_code}")
def get_unit_report(
    cycle_id: str,
    unit_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_unit_report_access(db, current_user, cycle_id, unit_code)
    try:
        data = EvaluationReportService(db).get_unit_report(cycle_id, unit_code)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data)


@router.get("/cycles/{cycle_id}/units/{unit_code}/members")
def get_unit_members(
    cycle_id: str,
    unit_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_unit_report_access(db, current_user, cycle_id, unit_code)
    try:
        data = EvaluationReportService(db).get_unit_report(cycle_id, unit_code)
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    return api_response(data=data["members"])


@router.get("/cycles/{cycle_id}/exports/members.csv")
def export_members_csv(
    cycle_id: str,
    unitCode: str | None = None,
    classification: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        payload = EvaluationExportService(db).export_members_csv(
            cycle_id, _filters(unitCode=unitCode, classification=classification)
        )
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    create_audit_log(
        db=db,
        action="EXPORT_EVALUATION_MEMBERS_CSV",
        resource_type="evaluation_cycle",
        resource_id=cycle_id,
        actor=current_user,
        after_snapshot={"unitCode": unitCode, "classification": classification},
    )
    db.commit()
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="evaluation_{cycle_id}_members.csv"'},
    )


@router.get("/cycles/{cycle_id}/exports/members.xlsx")
def export_members_xlsx(
    cycle_id: str,
    unitCode: str | None = None,
    classification: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        payload = EvaluationExportService(db).export_members_xlsx(
            cycle_id, _filters(unitCode=unitCode, classification=classification)
        )
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    create_audit_log(
        db=db,
        action="EXPORT_EVALUATION_MEMBERS_XLSX",
        resource_type="evaluation_cycle",
        resource_id=cycle_id,
        actor=current_user,
        after_snapshot={"unitCode": unitCode, "classification": classification},
    )
    db.commit()
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="evaluation_{cycle_id}_members.xlsx"'},
    )


@router.get("/cycles/{cycle_id}/exports/official-report.docx")
def export_official_report_docx(
    cycle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _require_roles(current_user, REPORT_MANAGER_ROLES)
    try:
        payload = EvaluationExportService(db).export_official_report_docx(
            cycle_id, actor=current_user
        )
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    create_audit_log(
        db=db,
        action="EXPORT_EVALUATION_OFFICIAL_DOCX",
        resource_type="evaluation_cycle",
        resource_id=cycle_id,
        actor=current_user,
    )
    db.commit()
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="evaluation_{cycle_id}_official.docx"'},
    )


@router.get("/cycles/{cycle_id}/members/{member_id}/exports/report.docx")
def export_member_report_docx(
    cycle_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _ensure_member_report_access(db, current_user, cycle_id, member_id)
    try:
        payload = EvaluationExportService(db).export_member_report_docx(
            cycle_id, member_id, actor=current_user
        )
    except EvaluationNotFoundError as exc:
        _raise_report_not_found(exc)
    create_audit_log(
        db=db,
        action="EXPORT_MEMBER_EVALUATION_REPORT",
        resource_type="member_evaluation",
        resource_id=member_id,
        actor=current_user,
        after_snapshot={"cycleId": cycle_id},
    )
    db.commit()
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="evaluation_{cycle_id}_{member_id}.docx"'},
    )
