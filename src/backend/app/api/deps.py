"""
FastAPI 通用依赖（认证鉴权 + DB Session 注入）。

所有需要登录的接口在路由参数中声明：
    current_user: dict = Depends(get_current_user)
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import UnauthorizedException
from app.core.security import WS_TICKET_PREFIX, decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    从 Bearer token 中解析用户信息。
    返回 {"sub": "admin", "version": <int>}，并验证 token_version 未被吊销。

    失败统一抛 UnauthorizedException（401）。
    """
    if credentials is None:
        raise UnauthorizedException()

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise UnauthorizedException("Token 无效或已过期")

    # 验证 token_version（修改密码后自动失效）
    from app.models.system_settings import SystemSettings
    settings_row = await db.get(SystemSettings, 1)
    if settings_row is None or payload.get("version") != settings_row.token_version:
        raise UnauthorizedException("Token 已失效，请重新登录")

    return payload


async def verify_ws_ticket(ticket: str) -> None:
    """
    验证并消费 WebSocket 一次性票据（60 秒有效、单次消费）。
    失败抛 HTTPException 403。
    """
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        key = f"{WS_TICKET_PREFIX}{ticket}"
        value = await client.get(key)
        if not value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效或已过期的 ws_ticket")
        await client.delete(key)   # 单次消费
    finally:
        await client.aclose()
