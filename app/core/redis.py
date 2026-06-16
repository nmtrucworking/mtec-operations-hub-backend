from __future__ import annotations

import logging
import time

import redis

from app.core.config import APP_ENV, REDIS_URL

logger = logging.getLogger(__name__)

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

_blacklist_fallback: dict[str, float] = {}
_redis_warning_logged = False


def _log_fallback_once(exc: Exception) -> None:
    global _redis_warning_logged
    if _redis_warning_logged:
        return
    _redis_warning_logged = True
    logger.warning(
        "[redis] Redis unavailable at %s. Using in-memory fallback for local runtime: %s",
        REDIS_URL,
        exc,
    )


def is_redis_available() -> bool:
    try:
        redis_client.ping()
        return True
    except redis.RedisError as exc:
        _log_fallback_once(exc)
        return False


def blacklist_token(token: str, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return

    if is_redis_available():
        redis_client.setex(f"blacklist:{token}", ttl_seconds, "revoked")
        return

    if APP_ENV != "production":
        _blacklist_fallback[token] = time.time() + ttl_seconds


def is_token_blacklisted(token: str) -> bool:
    if is_redis_available():
        return bool(redis_client.exists(f"blacklist:{token}"))

    if APP_ENV == "production":
        return False

    expires_at = _blacklist_fallback.get(token)
    if not expires_at:
        return False
    if expires_at <= time.time():
        _blacklist_fallback.pop(token, None)
        return False
    return True
