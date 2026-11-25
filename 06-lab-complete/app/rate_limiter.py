"""
Rate limiting (tiêu chí 7) — Sliding window 60 giây lưu trong Redis.
"""
import time
import uuid
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """
    Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây.
    Lưu state trong Redis sorted set để dùng chung giữa các workers và giữ state sau khi restart.
    """
    now = time.time()
    redis_key = f"ratelimit:{key}"
    limit = settings.rate_limit_per_minute

    try:
        r.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
        current_count = r.zcard(redis_key)
        if current_count >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        r.zadd(redis_key, {member: now})
        r.expire(redis_key, WINDOW_SECONDS)
    except HTTPException:
        raise
    except Exception:
        # Nếu Redis tạm thời không khả dụng khi chưa cấu hình, bỏ qua để không crash
        pass
