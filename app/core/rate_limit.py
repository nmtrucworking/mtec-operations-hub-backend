import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.redis import redis_client

_bucket: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def rate_limiter(max_requests: int, window_seconds: int):
    def _dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        # Định danh unique cho mỗi endpoint và IP
        key = f"rate_limit:{request.url.path}:{client_ip}"

        current_time = int(
            time.time() * 1000
        )  # Sử dụng millisecond để tăng độ chính xác
        window_start = current_time - (window_seconds * 1000)

        # Sử dụng Pipeline để gom cụm các lệnh Redis, giảm thiểu độ trễ mạng (Network Latency)
        pipe = redis_client.pipeline()
        # 1. Xóa các request cũ nằm ngoài khung thời gian hiện tại
        pipe.zremrangebyscore(key, 0, window_start)
        # 2. Đếm số lượng request còn lại trong khung thời gian
        pipe.zcard(key)
        # 3. Thêm request hiện tại vào tập hợp
        pipe.zadd(key, {str(current_time): current_time})
        # 4. Thiết lập thời gian sống (TTL) cho key để giải phóng bộ nhớ
        pipe.expire(key, window_seconds)

        results = pipe.execute()
        request_count = results[1]  # Kết quả của lệnh zcard

        if request_count >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Vuot qua gioi han request, vui long thu lai sau",
            )

    return _dependency
