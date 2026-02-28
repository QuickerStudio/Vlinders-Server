"""
Redis 缓存服务模块
"""
import redis.asyncio as redis
from typing import Optional, Any
import json

from .config import config
from .utils import logger


class CacheService:
    """Redis 缓存服务"""

    def __init__(self):
        self.client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """连接到 Redis"""
        if self.client:
            logger.warning("Redis client already exists")
            return

        try:
            logger.info(f"Connecting to Redis: {config.server.redis_url}")

            self.client = redis.from_url(
                config.server.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )

            # 测试连接
            await self.client.ping()

            logger.info("Redis connection established successfully")

        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """断开 Redis 连接"""
        if not self.client:
            return

        try:
            await self.client.close()
            self.client = None
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    async def get(self, key: str) -> Optional[str]:
        """获取缓存值"""
        if not self.client:
            raise RuntimeError("Redis client not initialized")

        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Error getting key {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> bool:
        """设置缓存值"""
        if not self.client:
            raise RuntimeError("Redis client not initialized")

        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            await self.client.set(key, value, ex=expire)
            return True
        except Exception as e:
            logger.error(f"Error setting key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存值"""
        if not self.client:
            raise RuntimeError("Redis client not initialized")

        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self.client:
            raise RuntimeError("Redis client not initialized")

        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking key {key}: {e}")
            return False

    async def incr(self, key: str, amount: int = 1) -> int:
        """递增计数器"""
        if not self.client:
            raise RuntimeError("Redis client not initialized")

        try:
            return await self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Error incrementing key {key}: {e}")
            raise

    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        if not self.client:
            raise RuntimeError("Redis client not initialized")

        try:
            return await self.client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Error setting expiry for key {key}: {e}")
            return False


# 全局缓存服务实例
cache = CacheService()
