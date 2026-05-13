from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typing import List

from app.core.audit import create_audit_log
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import Competition, CompetitionResult, User, Member
from app.schemas import CompetitionCreate, CompetitionResultCreate
from app.utils import generate_prefixed_id

router = APIRouter(prefix="/competitions", tags=["competitions"])

def _competition_out(comp: Competition) -> dict:
    return {
        "id": comp.id,
        "title": comp.title,
        "date": comp.date,
        "scale": comp.scale,
        "status": comp.status,
        "createdAt": getattr(comp, "created_at", None),
        "updatedAt": getattr(comp, "updated_at", None),
    }

@router.get("")
def list_competitions(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """
    Truy xuất danh sách các cuộc thi hiện có trong hệ thống.
    """
    stmt = select(Competition).order_by(Competition.date.desc())
    rows = db.scalars(stmt).all()
    return api_response(data=[_competition_out(row) for row in rows])

@router.post("")
def create_competition(
    body: CompetitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Khởi tạo một thực thể cuộc thi mới. 
    Yêu cầu quyền hạn từ Ban Chủ nhiệm (BCN).
    """
    if not current_user.has_any_roles({"bcn", "bcm"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền khởi tạo dữ liệu cuộc thi"
        )

    competition = Competition(
        id=generate_prefixed_id("COMP"),
        title=body.title,
        date=body.date,
        scale=body.scale,
        status=body.status or "Ongoing",
    )
    db.add(competition)
    db.flush()

    create_audit_log(
        db=db,
        action="CREATE_COMPETITION",
        resource_type="competition",
        resource_id=competition.id,
        actor=current_user,
        after_snapshot={
            "title": competition.title,
            "status": competition.status
        },
    )
    db.commit()
    db.refresh(competition)
    return api_response(data=_competition_out(competition))

@router.put("/{competition_id}/results")
def update_competition_results(
    competition_id: str,
    results: List[CompetitionResultCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Cập nhật hoặc ghi nhận kết quả đạt được của các thành viên trong một cuộc thi cụ thể.
    """
    if not current_user.has_any_roles({"bcn", "bcm"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền cập nhật kết quả cuộc thi"
        )

    competition = db.get(Competition, competition_id)
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy dữ liệu cuộc thi tương ứng"
        )

    # Loại bỏ các kết quả cũ để ghi nhận tập kết quả mới (Idempotent)
    db.execute(
        select(CompetitionResult).where(CompetitionResult.competition_id == competition_id)
    )
    # Triển khai logic ghi đè kết quả
    existing_results = db.scalars(
        select(CompetitionResult).where(CompetitionResult.competition_id == competition_id)
    ).all()
    for res in existing_results:
        db.delete(res)

    new_results = []
    for item in results:
        res_obj = CompetitionResult(
            competition_id=competition_id,
            member_id=item.memberId,
            achievement=item.achievement,
            bonus_kpi=item.bonusKpi,
            is_synced=False
        )
        db.add(res_obj)
        new_results.append(res_obj)

    create_audit_log(
        db=db,
        action="UPDATE_COMPETITION_RESULTS",
        resource_type="competition",
        resource_id=competition_id,
        actor=current_user,
        after_snapshot={"details": f"Cập nhật danh sách kết quả cho {len(new_results)} thành viên."}
    )
    
    db.commit()
    return api_response(data={"message": "Cập nhật kết quả thành công", "count": len(new_results)})