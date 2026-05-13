from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.errors import raise_api_error
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import Request, Transaction, User
from app.schemas import ReviewTransactionBody, TransactionCreate, TransactionUpdate
from app.utils import (
    generate_prefixed_id,
    get_required_approval_role,
    sanitize_pagination,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _tx_out(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "date": tx.date,
        "title": tx.title,
        "type": tx.type,
        "amount": tx.amount,
        "owner": tx.owner,
        "category": tx.category,
        "status": tx.status,
        "requiredApprovalRole": tx.required_approval_role,
        "reviewer": tx.reviewer,
        "reviewedAt": tx.reviewed_at,
        "approvalNote": tx.approval_note,
        "linkedRequestId": tx.linked_request_id,
        "linkedRequestType": tx.linked_request_type,
        "isDeleted": tx.is_deleted,
        "deletedAt": tx.deleted_at,
        "deletedBy": tx.deleted_by,
        "createdByUserId": tx.created_by_user_id,
        "createdAt": tx.created_at,
        "updatedAt": tx.updated_at,
    }


@router.get("")
def list_transactions(
    search: str | None = None,
    type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    fromDate: str | None = None,
    toDate: str | None = None,
    includeDeleted: bool = False,
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    page, pageSize = sanitize_pagination(page, pageSize)
    stmt = select(Transaction)
    count_stmt = select(func.count()).select_from(Transaction)

    filters = []
    if not includeDeleted:
        filters.append(Transaction.is_deleted.is_(False))
    if search:
        pattern = f"%{search}%"
        filters.append(
            (Transaction.title.ilike(pattern)) | (Transaction.owner.ilike(pattern))
        )
    if type:
        filters.append(Transaction.type == type)
    if status_filter:
        filters.append(Transaction.status == status_filter)
    if fromDate:
        filters.append(Transaction.date >= fromDate)
    if toDate:
        filters.append(Transaction.date <= toDate)

    if filters:
        stmt = stmt.where(and_(*filters))
        count_stmt = count_stmt.where(and_(*filters))

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()
    return api_response(
        data=[_tx_out(tx) for tx in rows],
        meta={"page": page, "pageSize": pageSize, "total": total},
    )


@router.get("/pending")
def list_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    stmt = select(Transaction).where(
        Transaction.status == "Cho duyet",
        Transaction.is_deleted.is_(False),
        Transaction.type == "Chi",
    )

    if current_user.has_role("bcn"):
        rows = db.scalars(stmt).all()
    elif current_user.has_role("bvh_finance"):
        rows = db.scalars(
            stmt.where(Transaction.required_approval_role == "bvh_finance")
        ).all()
    else:
        rows = []

    return api_response(data=[_tx_out(tx) for tx in rows])


@router.post("")
def create_transaction(
    body: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.has_any_roles({"bcn", "bvh_finance", "bvh_logistics", "bcm"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen tao giao dich"
        )
    if body.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="amount phai lon hon 0"
        )
    if body.type not in {"Thu", "Chi"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="type khong hop le"
        )

    status_value = "Da duyet" if body.type == "Thu" else "Cho duyet"
    required_role = (
        None if body.type == "Thu" else get_required_approval_role(body.category)
    )

    tx = Transaction(
        id=generate_prefixed_id("TX"),
        date=body.date,
        title=body.title,
        type=body.type,
        amount=body.amount,
        owner=body.owner,
        category=body.category,
        status=status_value,
        required_approval_role=required_role,
        reviewer=current_user.full_name if body.type == "Thu" else None,
        reviewed_at=datetime.now(UTC) if body.type == "Thu" else None,
        created_by_user_id=current_user.id,
    )
    db.add(tx)
    db.flush()
    create_audit_log(
        db=db,
        action="CREATE_TRANSACTION",
        resource_type="transaction",
        resource_id=tx.id,
        actor=current_user,
        after_snapshot={
            "title": tx.title,
            "type": tx.type,
            "amount": tx.amount,
            "status": tx.status,
        },
    )
    db.commit()
    db.refresh(tx)
    return api_response(data=_tx_out(tx))


@router.patch("/{tx_id}")
def update_transaction(
    tx_id: str,
    body: TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    tx = db.get(Transaction, tx_id)
    if not tx or tx.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay giao dich"
        )

    if not current_user.has_any_roles({"bcn", "bvh_finance", "bvh_logistics", "bcm"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen sua giao dich"
        )
    if tx.status != "Cho duyet":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chi duoc sua giao dich Cho duyet",
        )

    payload = body.model_dump(exclude_none=True)
    before = {
        "title": tx.title,
        "amount": tx.amount,
        "category": tx.category,
    }

    if "amount" in payload and payload["amount"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="amount phai lon hon 0"
        )

    for key, value in payload.items():
        setattr(tx, key, value)

    if "category" in payload and tx.type == "Chi":
        tx.required_approval_role = get_required_approval_role(tx.category)

    create_audit_log(
        db=db,
        action="UPDATE_TRANSACTION",
        resource_type="transaction",
        resource_id=tx.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "title": tx.title,
            "amount": tx.amount,
            "category": tx.category,
        },
    )
    db.commit()
    db.refresh(tx)
    return api_response(data=_tx_out(tx))


@router.post("/{tx_id}/review")
def review_transaction(
    tx_id: str,
    body: ReviewTransactionBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if body.status not in {"Da duyet", "Tu choi"}:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="TRANSACTION_REVIEW_INVALID_STATUS",
            message="status review khong hop le",
            details={"allowed": ["Da duyet", "Tu choi"]},
        )

    tx = db.get(Transaction, tx_id)
    if not tx or tx.is_deleted:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="TRANSACTION_NOT_FOUND",
            message="Khong tim thay giao dich",
        )
    if tx.status != "Cho duyet":
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="TRANSACTION_REVIEW_INVALID_STATE",
            message="Chi duoc review item dang Cho duyet",
            details={"currentStatus": tx.status},
        )

    if tx.required_approval_role == "bcn" and not current_user.has_role("bcn"):
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="TRANSACTION_REVIEW_ROLE_DENIED_BCN",
            message="Chi BCN duoc duyet giao dich nay",
        )

    if tx.required_approval_role == "bvh_finance" and not current_user.has_any_roles(
        {"bvh_finance", "bcn"}
    ):
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="TRANSACTION_REVIEW_ROLE_DENIED_FINANCE",
            message="Khong co quyen duyet giao dich nay",
        )

    if tx.type == "Chi" and not body.reviewNote:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="TRANSACTION_REVIEW_NOTE_REQUIRED",
            message="approvalNote khong duoc rong voi giao dich Chi",
        )

    before = {
        "status": tx.status,
        "reviewer": tx.reviewer,
        "reviewedAt": tx.reviewed_at,
        "approvalNote": tx.approval_note,
    }

    tx.status = body.status
    tx.reviewer = current_user.full_name
    tx.reviewed_at = datetime.now(UTC)
    tx.approval_note = body.reviewNote
    create_audit_log(
        db=db,
        action="REVIEW_TRANSACTION",
        resource_type="transaction",
        resource_id=tx.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "status": tx.status,
            "reviewer": tx.reviewer,
            "reviewedAt": tx.reviewed_at,
            "approvalNote": tx.approval_note,
        },
    )
    db.commit()
    db.refresh(tx)
    return api_response(data=_tx_out(tx))


@router.delete("/{tx_id}")
def soft_delete_transaction(
    tx_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.has_any_roles({"bcn", "bvh_finance"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen xoa giao dich"
        )

    tx = db.get(Transaction, tx_id)
    if not tx or tx.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay giao dich"
        )

    before = {
        "isDeleted": tx.is_deleted,
        "deletedAt": tx.deleted_at,
        "deletedBy": tx.deleted_by,
    }

    # Soft delete: set is_deleted flag and record deletion metadata
    tx.is_deleted = True
    tx.deleted_at = datetime.now(UTC)
    tx.deleted_by = current_user.full_name

    # If the transaction is linked to a request, we should also unlink it to maintain data integrity
    if tx.linked_request_id:
        req = db.get(Request, tx.linked_request_id)
        if req and req.linked_transaction_id == tx.id:
            req.linked_transaction_id = None

    create_audit_log(
        db=db,
        action="SOFT_DELETE_TRANSACTION",
        resource_type="transaction",
        resource_id=tx.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "isDeleted": tx.is_deleted,
            "deletedAt": tx.deleted_at,
            "deletedBy": tx.deleted_by,
        },
    )
    db.commit()
    db.refresh(tx)
    return api_response(data=_tx_out(tx))
