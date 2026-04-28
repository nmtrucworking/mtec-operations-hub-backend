from typing import Any


def api_response(
    data: Any = None, meta: dict[str, Any] | None = None, error: Any = None
) -> dict[str, Any]:
    return {
        "data": data,
        "meta": meta,
        "error": error,
    }
