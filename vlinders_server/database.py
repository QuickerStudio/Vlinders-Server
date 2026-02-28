"""
数据库连接管理模块
"""
import asyncpg
from typing import Optional
from contextlib import asynccontextmanager

from .config import config
from .utils import logger


class DatabaseManager:
    """PostgreSQL 数据库管理器"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """创建数据库连接池"""
        if self.pool:
            logger.warning("Database pool already exists")
            return

        try:
            logger.info(f"Connecting to database: {config.server.postgres_url}")

            self.pool = await asyncpg.create_pool(
                config.server.postgres_url,
                min_size=5,
                max_size=20,
                command_timeout=60,
                max_queries=50000,
                max_inactive_connection_lifetime=300
            )

            logger.info("Database connection pool created successfully")

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """关闭数据库连接池"""
        if not self.pool:
            return

        try:
            await self.pool.close()
            self.pool = None
            logger.info("Database connection pool closed")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")

    @asynccontextmanager
    async def acquire(self):
        """获取数据库连接"""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")

        async with self.pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, *args) -> str:
        """执行 SQL 语句"""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        """查询多行数据"""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        """查询单行数据"""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """查询单个值"""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)


# 全局数据库管理器实例
db = DatabaseManager()
