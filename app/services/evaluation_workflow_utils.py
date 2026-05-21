import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.evaluation_constants import CYCLE_MUTABLE_STATUSES
from app.models import EvaluationCycle
from app.services.evaluation_errors import EvaluationCycleLockedError


def metadata_load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {"legacyValue": value}
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def metadata_dump(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def utcnow() -> datetime:
    return datetime.now(UTC)


def add_business_days(start: datetime, days: int) -> datetime:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def ensure_cycle_is_mutable(cycle: EvaluationCycle) -> None:
    if cycle.status not in CYCLE_MUTABLE_STATUSES:
        raise EvaluationCycleLockedError(
            f"Evaluation cycle is not writable in status {cycle.status}: {cycle.id}"
        )
