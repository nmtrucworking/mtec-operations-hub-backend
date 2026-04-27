from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import Asset, Member, Request, Transaction, User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    total_members = db.scalar(select(func.count()).select_from(Member)) or 0

    fund_stmt = select(
        func.coalesce(
            func.sum(
                case((Transaction.type == "Thu", Transaction.amount), else_=-Transaction.amount)
            ),
            0,
        )
    ).where(Transaction.status == "Da duyet", Transaction.is_deleted.is_(False))
    current_fund = db.scalar(fund_stmt) or 0

    total_income = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.type == "Thu",
            Transaction.status == "Da duyet",
            Transaction.is_deleted.is_(False),
        )
    ) or 0

    total_expense = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.type == "Chi",
            Transaction.status == "Da duyet",
            Transaction.is_deleted.is_(False),
        )
    ) or 0

    maintenance_count = db.scalar(
        select(func.count()).select_from(Asset).where(Asset.status == "Can bao tri")
    ) or 0

    pending_requests_count = db.scalar(
        select(func.count()).select_from(Request).where(Request.status == "Cho duyet")
    ) or 0

    dept_distribution = [
        {"ban": row[0], "count": row[1]}
        for row in db.execute(
            select(Member.ban, func.count()).group_by(Member.ban).order_by(func.count().desc())
        )
    ]

    recent_activities = [
        {
            "id": row.id,
            "title": row.title,
            "type": row.type,
            "status": row.status,
            "createdAt": row.created_at,
        }
        for row in db.scalars(select(Transaction).order_by(Transaction.created_at.desc()).limit(10)).all()
    ]

    urgent_requests = [
        {
            "id": row.id,
            "name": row.name,
            "type": row.type,
            "date": row.date,
            "status": row.status,
        }
        for row in db.scalars(
            select(Request).where(Request.status == "Cho duyet").order_by(Request.date.asc()).limit(5)
        ).all()
    ]

    return api_response(
        data={
            "totalMembers": total_members,
            "currentFund": current_fund,
            "totalIncome": total_income,
            "totalExpense": total_expense,
            "maintenanceCount": maintenance_count,
            "pendingRequestsCount": pending_requests_count,
            "deptDistribution": dept_distribution,
            "recentActivities": recent_activities,
            "urgentRequests": urgent_requests,
        }
    )
