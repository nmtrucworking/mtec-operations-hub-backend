import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.rbac import require_roles
from app.core.response import api_response
from app.db import get_db
from app.models import Member, User
from app.schemas import MemberCreate, MemberUpdate
from app.utils import sanitize_pagination

router = APIRouter(prefix="/api/members", tags=["members"])


def _member_out(member: Member) -> dict:
    return {
        "id": member.id,
        "mssv": member.mssv,
        "name": member.name,
        "gender": member.gender,
        "dob": member.dob,
        "ban": member.ban,
        "roleTitle": member.role_title,
        "status": member.status,
        "phone": member.phone,
        "email": member.email,
        "joinDate": member.join_date,
        "lop": member.lop,
        "chuyenNganh": member.chuyen_nganh,
        "khoa": member.khoa,
        "address": member.address,
        "experience": member.experience,
        "goal": member.goal,
        "orientation": member.orientation,
        "createdAt": member.created_at,
        "updatedAt": member.updated_at,
    }


@router.get("")
def list_members(
    search: str | None = None,
    ban: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "bcn",
            "bvh_hr",
            "bcm",
            "member",
            "bvh_finance",
            "bvh_discipline",
            "bvh_logistics",
        )
    ),
) -> dict:
    page, pageSize = sanitize_pagination(page, pageSize)
    stmt = select(Member)
    count_stmt = select(func.count()).select_from(Member)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where((Member.name.ilike(pattern)) | (Member.mssv.ilike(pattern)))
        count_stmt = count_stmt.where(
            (Member.name.ilike(pattern)) | (Member.mssv.ilike(pattern))
        )
    if ban:
        stmt = stmt.where(Member.ban == ban)
        count_stmt = count_stmt.where(Member.ban == ban)
    if status_filter:
        stmt = stmt.where(Member.status == status_filter)
        count_stmt = count_stmt.where(Member.status == status_filter)

    total = db.scalar(count_stmt) or 0
    members = db.scalars(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()

    return api_response(
        data=[_member_out(member) for member in members],
        meta={"page": page, "pageSize": pageSize, "total": total},
    )


@router.get("/{member_id}")
def get_member(
    member_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "bcn",
            "bvh_hr",
            "bcm",
            "member",
            "bvh_finance",
            "bvh_discipline",
            "bvh_logistics",
        )
    ),
) -> dict:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay member"
        )
    return api_response(data=_member_out(member))


@router.post("")
def create_member(
    body: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn", "bvh_hr")),
) -> dict:
    if db.scalar(select(Member).where(Member.mssv == body.mssv)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="mssv da ton tai"
        )

    member = Member(
        mssv=body.mssv,
        name=body.name,
        gender=body.gender,
        dob=body.dob,
        ban=body.ban,
        role_title=body.roleTitle,
        status=body.status,
        phone=body.phone,
        email=str(body.email) if body.email else None,
        join_date=body.joinDate,
        lop=body.lop,
        chuyen_nganh=body.chuyenNganh,
        khoa=body.khoa,
        address=body.address,
        experience=body.experience,
        goal=body.goal,
        orientation=body.orientation,
    )
    db.add(member)
    create_audit_log(
        db=db,
        action="CREATE_MEMBER",
        resource_type="member",
        resource_id=member.id,
        actor=current_user,
        after_snapshot={
            "mssv": member.mssv,
            "name": member.name,
            "ban": member.ban,
            "status": member.status,
        },
    )
    db.commit()
    db.refresh(member)
    return api_response(data=_member_out(member))


@router.patch("/{member_id}")
def update_member(
    member_id: str,
    body: MemberUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn", "bvh_hr")),
) -> dict:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay member"
        )

    payload = body.model_dump(exclude_none=True)
    mapping = {
        "roleTitle": "role_title",
        "joinDate": "join_date",
        "chuyenNganh": "chuyen_nganh",
    }
    for key, value in payload.items():
        setattr(member, mapping.get(key, key), value)

    db.commit()
    db.refresh(member)
    return api_response(data=_member_out(member))


@router.patch("/{member_id}/status")
def update_member_status(
    member_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn", "bvh_hr")),
) -> dict:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay member"
        )

    new_status = body.get("status")
    if new_status not in {"Active", "Inactive"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="status khong hop le"
        )

    member.status = new_status
    db.commit()
    db.refresh(member)
    return api_response(data=_member_out(member))


@router.get("/export")
def export_members(
    format: str = Query(default="csv"),
    ban: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn", "bvh_hr")),
) -> StreamingResponse:
    if format != "csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Chi ho tro csv"
        )

    stmt = select(Member)
    if ban:
        stmt = stmt.where(Member.ban == ban)
    if status_filter:
        stmt = stmt.where(Member.status == status_filter)

    members = db.scalars(stmt).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "mssv", "name", "ban", "status", "phone", "email"])

    for m in members:
        writer.writerow([m.id, m.mssv, m.name, m.ban, m.status, m.phone, m.email])

    buffer.seek(0)
    headers = {"Content-Disposition": "attachment; filename=members.csv"}
    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv", headers=headers
    )
