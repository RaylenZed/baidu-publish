"""
认证路由（PRD §11.1）
  POST /auth/login        管理员登录，返回 JWT
  POST /auth/refresh      刷新 Token（旧 token 未过期时可直接换新）
  POST /auth/ws-ticket    签发 WebSocket 一次性票据（需已登录）
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse
from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.core.logging import get_logger
from app.core.security import (
    WS_TICKET_PREFIX,
    create_access_token,
    generate_ws_ticket,
    verify_password,
)
from app.middleware.rate_limit import check_login_rate_limit, reset_login_rate_limit
from app.models.system_settings import SystemSettings
from app.schemas.auth import LoginRequest, TokenResponse, WsTicketResponse

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/login",
    summary="管理员登录",
    response_model=ApiResponse[TokenResponse],
)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenResponse]:
    """
    验证密码 → 生成 JWT。

    安全措施：
    - 同 IP 5 分钟内最多 10 次尝试，超限锁定 15 分钟（CLAUDE.md §3 #12）
    - 密码比对 bcrypt hash（存于 system_settings.admin_password_hash）
    """
    client_ip = request.client.host if request.client else "unknown"
    await check_login_rate_limit(client_ip)

    row: SystemSettings | None = await db.get(SystemSettings, 1)
    if row is None:
        raise UnauthorizedException("系统尚未初始化，请检查服务配置")

    try:
        ok = verify_password(body.password, row.admin_password_hash)
    except Exception as exc:
        logger.warning(
            "密码校验失败（hash 异常）",
            extra={"error": str(exc), "client_ip": client_ip},
        )
        ok = False

    if not ok:
        raise UnauthorizedException("密码错误")

    token, expires_at = create_access_token("admin", row.token_version)
    await reset_login_rate_limit(client_ip)

    return ApiResponse.ok(
        TokenResponse(access_token=token, expires_at=expires_at)
    )


@router.post(
    "/refresh",
    summary="刷新 Token",
    response_model=ApiResponse[TokenResponse],
)
async def refresh_token(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenResponse]:
    """
    用有效 Token 换取新 Token（2 小时有效期重置）。
    旧 Token 立即不再使用，但直到过期前仍技术上有效（无黑名单）。
    """
    row: SystemSettings | None = await db.get(SystemSettings, 1)
    if row is None:
        raise UnauthorizedException("系统异常")

    token, expires_at = create_access_token(current_user["sub"], row.token_version)
    return ApiResponse.ok(TokenResponse(access_token=token, expires_at=expires_at))


@router.post(
    "/ws-ticket",
    summary="签发 WebSocket 一次性票据",
    response_model=ApiResponse[WsTicketResponse],
)
async def create_ws_ticket(
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[WsTicketResponse]:
    """
    生成 60 秒有效的一次性票据，供 WebSocket 连接鉴权使用（CLAUDE.md §3 #9）。
    票据存入 Redis，连接时消费（get + delete），不可重用。
    """
    ticket = generate_ws_ticket()
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        key = f"{WS_TICKET_PREFIX}{ticket}"
        await client.set(key, "1", ex=settings.WS_TICKET_EXPIRE_SECONDS)
    finally:
        await client.aclose()

    return ApiResponse.ok(WsTicketResponse(ticket=ticket))
