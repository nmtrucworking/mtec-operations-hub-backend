from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.errors import raise_api_error
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import Request, Transaction, User
from app.schemas import RequestCreate, RequestUpdate, ReviewRequestBody
from app.utils import generate_prefixed_id, get_required_approval_role, sanitize_pagination

router = APIRouter(prefix="/api/requests", tags=["requests"])


def _request_out(req: Request) -> dict:
    return {
        "id": req.id,
        "mssv": req.mssv,
        "name": req.name,
        "type": req.type,
        "date": req.date,
        "reason": req.reason,
        "status": req.status,
        "reviewer": req.reviewer,
        "reviewedAt": req.reviewed_at,
        "reviewNote": req.review_note,
        "linkedTransactionId": req.linked_transaction_id,
        "financeDraftEnabled": req.finance_draft_enabled,
        "financeDraftTitle": req.finance_draft_title,
        "financeDraftAmount": req.finance_draft_amount,
        "financeDraftType": req.finance_draft_type,
        "financeDraftCategory": req.finance_draft_category,
        "createdByUserId": req.created_by_user_id,
        "createdAt": req.created_at,
        "updatedAt": req.updated_at,
    }


@router.get("")
def list_requests(
    search: str | None = None,
    type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    page, pageSize = sanitize_pagination(page, pageSize)
    stmt = select(Request)
    count_stmt = select(func.count()).select_from(Request)

    if current_user.role == "member":
        stmt = stmt.where(Request.created_by_user_id == current_user.id)
        count_stmt = count_stmt.where(Request.created_by_user_id == current_user.id)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where((Request.name.ilike(pattern)) | (Request.mssv.ilike(pattern)))
        count_stmt = count_stmt.where((Request.name.ilike(pattern)) | (Request.mssv.ilike(pattern)))
    if type:
        stmt = stmt.where(Request.type == type)
        count_stmt = count_stmt.where(Request.type == type)
    if status_filter:
        stmt = stmt.where(Request.status == status_filter)
        count_stmt = count_stmt.where(Request.status == status_filter)

    total = db.scalar(count_stmt) or 0
    requests = db.scalars(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()
    return api_response(
        data=[_request_out(r) for r in requests],
        meta={"page": page, "pageSize": pageSize, "total": total},
    )


@router.get("/{request_id}")
def get_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay request")
    if current_user.role == "member" and req.created_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong duoc phep xem")
    return api_response(data=_request_out(req))


@router.post("")
def create_request(
    body: RequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if body.financeDraftAmount is not None and body.financeDraftAmount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="financeDraftAmount phai lon hon 0")

    req = Request(
        id=generate_prefixed_id("REQ"),
        mssv=body.mssv,
        name=body.name,
        type=body.type,
        date=body.date,
        reason=body.reason,
        status="Cho duyet",
        finance_draft_enabled=body.financeDraftEnabled,
        finance_draft_title=body.financeDraftTitle,
        finance_draft_amount=body.financeDraftAmount,
        finance_draft_type=body.financeDraftType,
        finance_draft_category=body.financeDraftCategory,
        created_by_user_id=current_user.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return api_response(data=_request_out(req))


@router.patch("/{request_id}")
def update_request(
    request_id: str,
    body: RequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay request")

    if current_user.role == "member" and req.created_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong duoc phep sua")
    if req.status != "Cho duyet":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chi duoc sua khi dang Cho duyet")

    payload = body.model_dump(exclude_none=True)
    mapping = {
        "financeDraftEnabled": "finance_draft_enabled",
        "financeDraftTitle": "finance_draft_title",
        "financeDraftAmount": "finance_draft_amount",
        "financeDraftType": "finance_draft_type",
        "financeDraftCategory": "finance_draft_category",
    }
    if "financeDraftAmount" in payload and payload["financeDraftAmount"] <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="financeDraftAmount phai lon hon 0")

    for key, value in payload.items():
        setattr(req, mapping.get(key, key), value)

    db.commit()
    db.refresh(req)
    return api_response(data=_request_out(req))


@router.post("/{request_id}/review")
def review_request(
    request_id: str,
    body: ReviewRequestBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role not in {"bcn", "bvh_hr"}:
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="REQUEST_REVIEW_FORBIDDEN",
            message="Khong co quyen duyet request",
        )

    if body.status not in {"Da duyet", "Tu choi"}:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="REQUEST_REVIEW_INVALID_STATUS",
            message="status review khong hop le",
            details={"allowed": ["Da duyet", "Tu choi"]},
        )

    req = db.get(Request, request_id)
    if not req:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="REQUEST_NOT_FOUND",
            message="Khong tim thay request",
        )
    if req.status != "Cho duyet":
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="REQUEST_REVIEW_INVALID_STATE",
            message="Chi duoc review request dang Cho duyet",
            details={"currentStatus": req.status},
        )

    before = {
        "status": req.status,
        "reviewer": req.reviewer,
        "reviewedAt": req.reviewed_at,
        "reviewNote": req.review_note,
        "linkedTransactionId": req.linked_transaction_id,
    }

    req.status = body.status
    req.reviewer = current_user.full_name
    req.reviewed_at = datetime.utcnow()
    req.review_note = body.reviewNote

    if body.status == "Da duyet" and req.finance_draft_enabled:
        if req.linked_transaction_id:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="REQUEST_ALREADY_LINKED_TRANSACTION",
                message="Request da lien ket transaction truoc do",
                details={"linkedTransactionId": req.linked_transaction_id},
            )
        if not req.finance_draft_amount or req.finance_draft_amount <= 0:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="REQUEST_FINANCE_DRAFT_INVALID_AMOUNT",
                message="Finance draft amount khong hop le",
            )
        if not req.finance_draft_type or not req.finance_draft_category or not req.finance_draft_title:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="REQUEST_FINANCE_DRAFT_INCOMPLETE",
                message="Finance draft chua day du",
            )

        tx_type = req.finance_draft_type
        if tx_type not in {"Thu", "Chi"}:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="REQUEST_FINANCE_DRAFT_INVALID_TYPE",
                message="financeDraftType khong hop le",
                details={"allowed": ["Thu", "Chi"]},
            )

        status_value = "Da duyet" if tx_type == "Thu" else "Cho duyet"
        required_role = None if tx_type == "Thu" else get_required_approval_role(req.finance_draft_category)

        tx = Transaction(
            id=generate_prefixed_id("TX"),
            date=req.date,
            title=req.finance_draft_title,
            type=tx_type,
            amount=req.finance_draft_amount,
            owner=req.name,
            category=req.finance_draft_category,
            status=status_value,
            required_approval_role=required_role,
            reviewer=current_user.full_name if tx_type == "Thu" else None,
            reviewed_at=datetime.utcnow() if tx_type == "Thu" else None,
            linked_request_id=req.id,
            linked_request_type=req.type,
            created_by_user_id=req.created_by_user_id,
        )
        db.add(tx)
        db.flush()
        req.linked_transaction_id = tx.id

    create_audit_log(
        db=db,
        action="REVIEW_REQUEST",
        resource_type="request",
        resource_id=req.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "status": req.status,
            "reviewer": req.reviewer,
            "reviewedAt": req.reviewed_at,
            "reviewNote": req.review_note,
            "linkedTransactionId": req.linked_transaction_id,
        },
    )

    db.commit()
    db.refresh(req)
    return api_response(data=_request_out(req))
