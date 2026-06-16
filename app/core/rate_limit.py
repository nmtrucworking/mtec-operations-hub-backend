from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

import redis
from fastapi import HTTPException, Request, status

from app.core.redis import is_redis_available, redis_client

_bucket: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _memory_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    now = time.time()
    window_start = now - window_seconds
    with _lock:
        bucket = _bucket[key]
        while bucket and bucket[0] <= window_start:
            bucket.popleft()
        if len(bucket) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Vuot qua gioi han request, vui long thu lai sau",
            )
        bucket.append(now)


def rate_limiter(max_requests: int, window_seconds: int):
    def _dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{request.url.path}:{client_ip}"

        if not is_redis_available():
            _memory_rate_limit(key, max_requests, window_seconds)
            return

        current_time = int(time.time() * 1000)
        request_member = f"{current_time}:{time.time_ns()}"
        window_start = current_time - (window_seconds * 1000)

        try:
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {request_member: current_time})
            pipe.expire(key, window_seconds)
            results = pipe.execute()
            request_count = results[1]
        except redis.RedisError:
            _memory_rate_limit(key, max_requests, window_seconds)
            return

        if request_count >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Vuot qua gioi han request, vui long thu lai sau",
            )

    return _dependency
