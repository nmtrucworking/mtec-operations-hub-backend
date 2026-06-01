from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.rbac import require_roles
from app.core.response import api_response
from app.core.security import get_password_hash
from app.db import get_db
from app.models import Role, User, UserRole
from app.schemas import ResetPasswordRequest, UserCreate, UserStatusUpdate, UserUpdate
from app.utils import sanitize_pagination

router = APIRouter(prefix="/users", tags=["users"])


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "studentId": user.student_id,
        "fullName": user.full_name,
        "role": user.primary_role,
        "roles": user.role_names,
        "avatarInitials": user.avatar_initials,
        "email": user.email,
        "phone": user.phone,
        "isActive": user.is_active,
        "createdAt": user.created_at,
        "updatedAt": user.updated_at,
    }


def _resolve_roles_payload(role: str | None, roles: list[str] | None) -> list[str]:
    normalized: list[str] = []
    if roles:
        normalized.extend([item.strip() for item in roles if item and item.strip()])
    if role and role.strip():
        normalized.append(role.strip())

    deduped = sorted(set(normalized))
    return deduped or ["member"]


def _pick_primary_role(role_names: list[str]) -> str:
    priorities = {
        "bcn": 0,
        "bvh_finance": 1,
        "bvh_hr": 2,
        "bvh_discipline": 3,
        "bvh_logistics": 4,
        "bcm": 5,
        "member": 6,
    }
    return min(role_names, key=lambda item: priorities.get(item, 999))


def _sync_user_roles(db: Session, user: User, role_names: list[str]) -> None:
    roles = db.scalars(select(Role).where(Role.name.in_(role_names))).all()
    role_by_name = {role.name: role for role in roles}

    for role_name in role_names:
        if role_name not in role_by_name:
            role_obj = Role(name=role_name)
            db.add(role_obj)
            db.flush()
            role_by_name[role_name] = role_obj

    desired_role_ids = {role_by_name[name].id for name in role_names}
    existing = {item.role_id: item for item in user.user_roles}

    for role_id, user_role in list(existing.items()):
        if role_id not in desired_role_ids:
            db.delete(user_role)

    existing_role_ids = set(existing.keys())
    for role_id in desired_role_ids:
        if role_id not in existing_role_ids:
            db.add(UserRole(user_id=user.id, role_id=role_id))

    user.role = _pick_primary_role(role_names)


@router.get("")
def list_users(
    search: str | None = None,
    role: str | None = None,
    includeInactive: bool = Query(default=False),
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn")),
) -> dict:
    page, pageSize = sanitize_pagination(page, pageSize)

    stmt = select(User).distinct()
    if not includeInactive:
        stmt = stmt.where(User.is_active.is_(True))

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (User.username.ilike(pattern)) | (User.full_name.ilike(pattern))
        )

    if role:
        stmt = stmt.outerjoin(UserRole, UserRole.user_id == User.id).outerjoin(
            Role, Role.id == UserRole.role_id
        )
        stmt = stmt.where(or_(User.role == role, Role.name == role))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    users = db.scalars(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()
    return api_response(
        data=[_user_out(u) for u in users],
        meta={"page": page, "pageSize": pageSize, "total": total},
    )


@router.post("")
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="username da ton tai"
        )

    roles_payload = _resolve_roles_payload(body.role, body.roles)

    user = User(
        username=body.username,
        password_hash=get_password_hash(body.password),
        full_name=body.fullName,
        role=roles_payload[0],
        avatar_initials=body.avatarInitials,
        email=body.email,
        phone=body.phone,
        is_active=True,
    )
    db.add(user)
    db.flush()
    _sync_user_roles(db, user, roles_payload)
    create_audit_log(
        db=db,
        action="CREATE_USER",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
        after_snapshot={
            "username": user.username,
            "full_name": user.full_name,
            "role": user.primary_role,
            "roles": user.role_names,
        },
    )
    db.commit()
    db.refresh(user)
    return api_response(data=_user_out(user))


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay user"
        )

    payload = body.model_dump(exclude_none=True)
    before = {
        "full_name": user.full_name,
        "role": user.primary_role,
        "roles": user.role_names,
        "email": user.email,
    }

    mapping = {
        "fullName": "full_name",
        "avatarInitials": "avatar_initials",
    }

    roles_payload = None
    if "roles" in payload or "role" in payload:
        roles_payload = _resolve_roles_payload(payload.get("role"), payload.get("roles"))
    payload.pop("role", None)
    payload.pop("roles", None)

    for key, value in payload.items():
        setattr(user, mapping.get(key, key), value)

    if roles_payload:
        _sync_user_roles(db, user, roles_payload)

    create_audit_log(
        db=db,
        action="UPDATE_USER",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "full_name": user.full_name,
            "role": user.primary_role,
            "roles": user.role_names,
            "email": user.email,
        },
    )
    db.commit()
    db.refresh(user)
    return api_response(data=_user_out(user))


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay user"
        )

    user.password_hash = get_password_hash(body.newPassword)
    create_audit_log(
        db=db,
        action="RESET_PASSWORD",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
    )
    db.commit()
    return api_response(data={"message": "Dat lai mat khau thanh cong"})


@router.patch("/{user_id}/status")
def update_status(
    user_id: str,
    body: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay user"
        )

    before = {"is_active": user.is_active}
    user.is_active = body.isActive
    create_audit_log(
        db=db,
        action="UPDATE_USER_STATUS",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={"is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return api_response(data=_user_out(user))


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay user"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Khong the xoa tai khoan dang dang nhap",
        )

    before = {
        "username": user.username,
        "full_name": user.full_name,
        "role": user.primary_role,
        "roles": user.role_names,
        "email": user.email,
        "is_active": user.is_active,
    }

    user.is_active = False
    create_audit_log(
        db=db,
        action="DELETE_USER",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={"is_active": user.is_active},
    )
    db.commit()

    return api_response(data={"message": "Da vo hieu hoa tai khoan"})

@router.get("/{user_id}")
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn")),
) -> dict:
    """
    Truy xuất thông tin chi tiết của một tài khoản người dùng cụ thể từ cơ sở dữ liệu.
    
    Quy trình xử lý:
    1. Tiếp nhận tham số định danh user_id từ yêu cầu của người dùng.
    2. Thực hiện truy vấn trực tiếp vào bảng User thông qua cơ chế ORM của SQLAlchemy.
    3. Kiểm tra tính hiện hữu của bản ghi: Nếu không tồn tại, hệ thống phản hồi lỗi 404 (Not Found).
    4. Trả về dữ liệu đã được chuẩn hóa thông qua hàm hỗ trợ _user_out.
    
    Yêu cầu quyền hạn: Chỉ các tài khoản thuộc Ban Chủ nhiệm (bcn) mới được phép thực thi tác vụ này.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Không tìm thấy tài khoản người dùng yêu cầu"
        )
    
    return api_response(data=_user_out(user))