from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.evaluation_constants import CYCLE_STATUS_LOCKED
from app.models import EvaluationCycle


@dataclass
class CachedReport:
    payload: dict[str, Any]
    cached_at: datetime


class EvaluationReportCacheService:
    """Small in-process cache for immutable locked-cycle dashboard reports."""

    _cache: dict[str, CachedReport] = {}

    @classmethod
    def make_key(
        cls, *, cycle_id: str, report_type: str, filters: dict[str, Any] | None = None
    ) -> str:
        serialized_filters = json.dumps(filters or {}, sort_keys=True, default=str)
        return f"{cycle_id}:{report_type}:{serialized_filters}"

    @classmethod
    def get(cls, key: str) -> dict[str, Any] | None:
        cached = cls._cache.get(key)
        if not cached:
            return None
        payload = dict(cached.payload)
        payload.setdefault("cache", {})
        payload["cache"] = {"cacheable": True, "cachedAt": cached.cached_at.isoformat()}
        return payload

    @classmethod
    def set_if_cacheable(
        cls, key: str, cycle: EvaluationCycle, payload: dict[str, Any]
    ) -> dict[str, Any]:
        cacheable = cycle.status == CYCLE_STATUS_LOCKED
        output = dict(payload)
        output["cache"] = {"cacheable": cacheable, "cachedAt": None}
        if cacheable:
            cached_at = datetime.now(UTC)
            output["cache"] = {"cacheable": True, "cachedAt": cached_at.isoformat()}
            cls._cache[key] = CachedReport(payload=dict(output), cached_at=cached_at)
        return output

    @classmethod
    def invalidate_cycle(cls, cycle_id: str) -> None:
        prefix = f"{cycle_id}:"
        for key in list(cls._cache):
            if key.startswith(prefix):
                cls._cache.pop(key, None)
