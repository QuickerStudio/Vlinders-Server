"""
API 限流中间件
"""
from fastapi import HTTPException, Request, status
from typing import Optional
import time

from .cache import cache
from .utils import logger


class RateLimiter:
    """基于 Redis 的 API 限流器"""

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

    async def check_rate_limit(
        self,
        identifier: str,
        endpoint: Optional[str] = None
    ) -> bool:
        """
        检查是否超过限流

        Args:
            identifier: 用户标识（user_id 或 IP）
            endpoint: API 端点（可选）

        Returns:
            是否允许请求
        """
        current_time = int(time.time())
        minute_key = f"ratelimit:{identifier}:minute:{current_time // 60}"
        hour_key = f"ratelimit:{identifier}:hour:{current_time // 3600}"

        # 检查每分钟限制
        minute_count = await cache.incr(minute_key)
        if minute_count == 1:
            await cache.expire(minute_key, 60)

        if minute_count > self.requests_per_minute:
            logger.warning(
                f"Rate limit exceeded for {identifier}: "
                f"{minute_count} requests in current minute"
            )
            return False

        # 检查每小时限制
        hour_count = await cache.incr(hour_key)
        if hour_count == 1:
            await cache.expire(hour_key, 3600)

        if hour_count > self.requests_per_hour:
            logger.warning(
                f"Rate limit exceeded for {identifier}: "
                f"{hour_count} requests in current hour"
            )
            return False

        return True

    async def get_remaining_requests(
        self,
        identifier: str
    ) -> dict:
        """
        获取剩余请求次数

        Returns:
            包含剩余次数的字典
        """
        current_time = int(time.time())
        minute_key = f"ratelimit:{identifier}:minute:{current_time // 60}"
        hour_key = f"ratelimit:{identifier}:hour:{current_time // 3600}"

        minute_count = int(await cache.get(minute_key) or 0)
        hour_count = int(await cache.get(hour_key) or 0)

        return {
            "requests_per_minute": self.requests_per_minute,
            "remaining_minute": max(0, self.requests_per_minute - minute_count),
            "requests_per_hour": self.requests_per_hour,
            "remaining_hour": max(0, self.requests_per_hour - hour_count)
        }


# 全局限流器实例
rate_limiter = RateLimiter()


async def check_rate_limit(request: Request) -> None:
    """
    限流中间件依赖项

    用于 FastAPI 路由的 Depends
    """
    # 从请求中获取用户标识
    # 优先使用认证用户 ID，否则使用 IP 地址
    identifier = getattr(request.state, "user_id", None)
    if not identifier:
        identifier = request.client.host

    # 检查限流
    allowed = await rate_limiter.check_rate_limit(identifier)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
