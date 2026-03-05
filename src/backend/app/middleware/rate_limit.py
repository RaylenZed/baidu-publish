"""
登录限流（PRD §14 / CLAUDE.md 安全基线）：
  同 IP 5 分钟内最多 10 次登录尝试，超限锁定 15 分钟。

实现：Redis incr + expire，key = login_attempt:{ip}
调用方：auth.py 路由在调用密码校验前调用 check_login_rate_limit()。
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import LoginRateLimitException

_MAX_ATTEMPTS = 10
_WINDOW_SECONDS = 5 * 60       # 5 分钟
_LOCKOUT_SECONDS = 15 * 60     # 锁定 15 分钟


def _redis_client() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_login_rate_limit(ip: str) -> None:
    """
    检查登录频率；超限时抛 LoginRateLimitException。
    每次调用自动计数 +1。
    """
    client = _redis_client()
    key = f"login_attempt:{ip}"
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, _WINDOW_SECONDS)
        if count > _MAX_ATTEMPTS:
            # 锁定期延长到 15 分钟
            await client.expire(key, _LOCKOUT_SECONDS)
            raise LoginRateLimitException()
    finally:
        await client.aclose()


async def reset_login_rate_limit(ip: str) -> None:
    """登录成功后重置计数（可选调用）。"""
    client = _redis_client()
    try:
        await client.delete(f"login_attempt:{ip}")
    finally:
        await client.aclose()
