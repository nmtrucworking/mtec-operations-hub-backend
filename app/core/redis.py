import redis
from app.core.config import REDIS_URL

# Khởi tạo Connection Pool. decode_responses=True giúp tự động chuyển đổi dữ liệu bytes về string.
redis_client = redis.from_url(REDIS_URL, decode_responses=True)