from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import raise_api_error
from app.core.rate_limit import rate_limiter
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import AIGenerationLog, User
from app.schemas import AIGenerateDraftBody, AIGenerateInsightBody
from app.services.ai_provider import AIProviderError, generate_text

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _persist_ai_log(
    db: Session,
    user: User,
    module: str,
    prompt: str,
    response_text: str,
    provider: str,
    status: str = "success",
) -> AIGenerationLog:
    log = AIGenerationLog(
        user_id=user.id,
        module=module,
        prompt=prompt,
        response_text=response_text,
        provider=provider,
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
    try:
        text, provider = generate_text(prompt=body.prompt)
        log = _persist_ai_log(
            db=db,
            user=current_user,
            module="dashboard",
            prompt=body.prompt,
            response_text=text,
            provider=provider,
        )
    except AIProviderError as exc:
        _persist_ai_log(
            db=db,
            user=current_user,
            module="dashboard",
            prompt=body.prompt,
            response_text=exc.message,
            provider="gemini",
            status="failed",
        )
        raise_api_error(status_code=exc.status_code, code=exc.code, message=exc.message)

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
    try:
        text, provider = generate_text(prompt=body.prompt, context=body.context)
        log = _persist_ai_log(
            db=db,
            user=current_user,
            module="generator",
            prompt=body.prompt,
            response_text=text,
            provider=provider,
        )
    except AIProviderError as exc:
        _persist_ai_log(
            db=db,
            user=current_user,
            module="generator",
            prompt=body.prompt,
            response_text=exc.message,
            provider="gemini",
            status="failed",
        )
        raise_api_error(status_code=exc.status_code, code=exc.code, message=exc.message)

    return api_response(
        data={
            "text": text,
            "logId": log.id,
            "provider": log.provider,
            "status": log.status,
        }
    )
