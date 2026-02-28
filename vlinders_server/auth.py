"""
认证和授权中间件
"""
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import jwt
from datetime import datetime, timedelta

from .config import config
from .utils import logger


security = HTTPBearer()


class AuthService:
    """认证服务"""

    def __init__(self):
        self.secret_key = config.server.internal_secret
        self.algorithm = "HS256"

    def create_token(
        self,
        user_id: str,
        tenant_id: str,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建 JWT token"""
        if expires_delta is None:
            expires_delta = timedelta(hours=24)

        expire = datetime.utcnow() + expires_delta

        payload = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "exp": expire,
            "iat": datetime.utcnow()
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str) -> dict:
        """验证 JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

    def verify_internal_secret(self, secret: str) -> bool:
        """验证内部密钥"""
        return secret == self.secret_key


# 全局认证服务实例
auth_service = AuthService()


async def verify_internal_auth(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    验证内部认证

    用于内部服务之间的通信
    """
    token = credentials.credentials

    # 检查是否是内部密钥
    if auth_service.verify_internal_secret(token):
        return {"type": "internal", "authenticated": True}

    # 否则验证 JWT token
    payload = auth_service.verify_token(token)
    return {
        "type": "jwt",
        "authenticated": True,
        "user_id": payload.get("user_id"),
        "tenant_id": payload.get("tenant_id")
    }


async def verify_user_auth(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    验证用户认证

    用于用户 API 请求
    """
    token = credentials.credentials
    payload = auth_service.verify_token(token)

    return {
        "user_id": payload.get("user_id"),
        "tenant_id": payload.get("tenant_id")
    }
