from typing import Any


def api_response(
    data: Any = None,
    meta: dict[str, Any] | None = None,
    error: Any = None,
    message: str | None = None,
) -> dict[str, Any]:
    if message and isinstance(data, dict) and "message" not in data:
        data = {**data, "message": message}

    return {
        "data": data,
        "meta": meta,
        "error": error,
    }
