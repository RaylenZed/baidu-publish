"""
全局配置：从环境变量读取，使用 Pydantic Settings。

所有必填项在 .env.example 中列出。
启动时若缺少必填 env var，Pydantic 会立刻抛出 ValidationError，阻止应用启动。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 应用 ─────────────────────────────────────────────────────────────────
    APP_TITLE: str = "百家号自动化内容发布管理系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    APP_TIMEZONE: str = "Asia/Shanghai"

    # ── 认证 ─────────────────────────────────────────────────────────────────
    ADMIN_PASSWORD: str                       # 初始管理员密码，首次启动写入 DB
    JWT_SECRET_KEY: str                       # JWT 签名密钥，随机 32+ 字符
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120   # 2 小时
    WS_TICKET_EXPIRE_SECONDS: int = 60

    # ── Cookie 加密 ──────────────────────────────────────────────────────────
    COOKIE_SECRET_KEY: str                    # AES-256 密钥，32 字节 hex 字符串

    # ── 数据库 ───────────────────────────────────────────────────────────────
    DATABASE_URL: str                         # postgresql+asyncpg://user:pass@host:5432/db
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── CORS ─────────────────────────────────────────────────────────────────
    # 用 str 类型避免 pydantic-settings 对 list[str] 做预解码（JSON parse 会阻断 validator）
    # 支持逗号分隔格式：http://a.com,http://b.com
    # 支持 JSON 数组格式：["http://a.com","http://b.com"]
    # 使用 settings.cors_origins_list 属性获取解析后列表
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:80"

    @property
    def cors_origins_list(self) -> list[str]:
        """解析 CORS_ORIGINS，支持逗号串与 JSON 数组两种格式。"""
        v = self.CORS_ORIGINS.strip()
        if v.startswith("["):
            import json
            return json.loads(v)
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    # ── Celery ───────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = ""               # 留空时从 REDIS_URL 推导
    CELERY_RESULT_BACKEND: str = ""

    @field_validator("CELERY_BROKER_URL", mode="before")
    @classmethod
    def set_broker(cls, v: str, info) -> str:
        if not v:
            redis_url = info.data.get("REDIS_URL", "redis://localhost:6379/0")
            return redis_url
        return v

    @field_validator("CELERY_RESULT_BACKEND", mode="before")
    @classmethod
    def set_backend(cls, v: str, info) -> str:
        if not v:
            redis_url = info.data.get("REDIS_URL", "redis://localhost:6379/0")
            return redis_url
        return v

    # ── 日志 ─────────────────────────────────────────────────────────────────
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"   # 生产用 json，本地调试用 text


@lru_cache
def get_settings() -> Settings:
    """单例：全局配置对象，通过 Depends(get_settings) 注入。"""
    return Settings()


# 模块级全局实例，方便非 DI 场景直接导入
settings: Settings = get_settings()
