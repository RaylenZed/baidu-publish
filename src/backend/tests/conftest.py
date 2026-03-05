"""
测试全局配置。

在任何 app 模块导入之前：
1. 强制覆盖（非 setdefault）所有必要 env vars
2. Patch create_async_engine，避免在无 asyncpg 的本地环境中因模块级 engine 初始化失败
"""
import os
from unittest.mock import AsyncMock, MagicMock

# ── 强制覆盖环境变量（必须在所有 app 导入之前）───────────────────────────────

os.environ["ADMIN_PASSWORD"] = "test_admin_password_123"
os.environ["JWT_SECRET_KEY"] = "test-super-secret-jwt-key-1234567890abcdef"
# COOKIE_SECRET_KEY 需要恰好 64 个十六进制字符（32 字节）
os.environ["COOKIE_SECRET_KEY"] = "deadbeef" * 8
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test_db"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"

# ── Patch create_async_engine（database.py 在模块级创建 engine）──────────────
# 避免 asyncpg 未安装或 DB 不可达时导致 import 失败。
# 集成测试通过 FastAPI dependency_overrides 完全绕过真实 DB，engine mock 无影响。

from sqlalchemy.ext import asyncio as _sqla_asyncio  # noqa: E402

_real_create_async_engine = _sqla_asyncio.create_async_engine


def _mock_create_async_engine(url, **kwargs):
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    return mock_engine


_sqla_asyncio.create_async_engine = _mock_create_async_engine

# ── 清除 lru_cache，确保使用上方测试 env vars 重建 Settings ─────────────────

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
