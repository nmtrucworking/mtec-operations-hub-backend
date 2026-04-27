from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request, status

_bucket: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def rate_limiter(max_requests: int, window_seconds: int) -> Callable:
    def _dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{client_ip}"
        now = monotonic()
        threshold = now - window_seconds

        with _lock:
            queue = _bucket[key]
            while queue and queue[0] <= threshold:
                queue.popleft()

            if len(queue) >= max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Vuot qua gioi han request, vui long thu lai sau",
                )

            queue.append(now)

    return _dependency
