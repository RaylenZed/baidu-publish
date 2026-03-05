"""
认证相关 Pydantic Schema（请求体 + 响应体）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, description="管理员密码")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int = 60   # 秒
