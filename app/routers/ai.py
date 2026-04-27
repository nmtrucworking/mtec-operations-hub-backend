from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limiter
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import AIGenerationLog, User
from app.schemas import AIGenerateDraftBody, AIGenerateInsightBody

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _persist_ai_log(
    db: Session,
    user: User,
    module: str,
    prompt: str,
    response_text: str,
    status: str = "success",
) -> AIGenerationLog:
    log = AIGenerationLog(
        user_id=user.id,
        module=module,
        prompt=prompt,
        response_text=response_text,
        provider="gemini",
        status=status,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.post("/generate-insight", dependencies=[Depends(rate_limiter(max_requests=10, window_seconds=60))])
def generate_insight(
    body: AIGenerateInsightBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Placeholder response until external provider integration is completed.
    text = f"[INSIGHT DRAFT] {body.prompt.strip()}"
    log = _persist_ai_log(
        db=db,
        user=current_user,
        module="dashboard",
        prompt=body.prompt,
        response_text=text,
    )
    return api_response(
        data={
            "text": text,
            "logId": log.id,
            "provider": log.provider,
            "status": log.status,
        }
    )


@router.post("/generate-draft", dependencies=[Depends(rate_limiter(max_requests=10, window_seconds=60))])
def generate_draft(
    body: AIGenerateDraftBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    context_text = f"\nContext: {body.context}" if body.context else ""
    text = f"[DOCUMENT DRAFT] {body.prompt.strip()}{context_text}"
    log = _persist_ai_log(
        db=db,
        user=current_user,
        module="generator",
        prompt=body.prompt,
        response_text=text,
    )
    return api_response(
        data={
            "text": text,
            "logId": log.id,
            "provider": log.provider,
            "status": log.status,
        }
    )
