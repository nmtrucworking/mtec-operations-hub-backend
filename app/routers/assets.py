from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import Asset, User
from app.schemas import AssetCreate, AssetUpdate
from app.utils import generate_prefixed_id, sanitize_pagination

router = APIRouter(prefix="/api/assets", tags=["assets"])


def _asset_out(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "name": asset.name,
        "quantity": asset.quantity,
        "status": asset.status,
        "holder": asset.holder,
        "category": asset.category,
        "createdAt": asset.created_at,
        "updatedAt": asset.updated_at,
    }


@router.get("")
def list_assets(
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    page, pageSize = sanitize_pagination(page, pageSize)

    stmt = select(Asset)
    count_stmt = select(func.count()).select_from(Asset)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Asset.name.ilike(pattern))
        count_stmt = count_stmt.where(Asset.name.ilike(pattern))

    if status_filter:
        stmt = stmt.where(Asset.status == status_filter)
        count_stmt = count_stmt.where(Asset.status == status_filter)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()
    return api_response(
        data=[_asset_out(row) for row in rows],
        meta={"page": page, "pageSize": pageSize, "total": total},
    )


@router.get("/{asset_id}")
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay tai san"
        )
    return api_response(data=_asset_out(asset))


@router.post("")
def create_asset(
    body: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role not in {"bcn", "bvh_logistics"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen tao tai san"
        )

    asset = Asset(
        id=generate_prefixed_id("TS"),
        name=body.name,
        quantity=body.quantity,
        status=body.status,
        holder=body.holder,
        category=body.category,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return api_response(data=_asset_out(asset))


@router.patch("/{asset_id}")
def update_asset(
    asset_id: str,
    body: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role not in {"bcn", "bvh_logistics"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Khong co quyen cap nhat tai san",
        )

    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay tai san"
        )

    payload = body.model_dump(exclude_none=True)
    for key, value in payload.items():
        setattr(asset, key, value)

    db.commit()
    db.refresh(asset)
    return api_response(data=_asset_out(asset))
