"""
数据库连接管理（SQLAlchemy 2.0 async）。

连接串格式：postgresql+asyncpg://user:pass@host:5432/db_name
时区约定：数据库存储 UTC，通过 TIMESTAMPTZ 字段保证。
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

# ── 引擎 ─────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,           # DEBUG 模式打印 SQL
    future=True,
)

# ── Session 工厂 ─────────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,        # 避免 commit 后访问属性触发额外查询
    autoflush=False,
    autocommit=False,
)

logger = get_logger(__name__)


# ── FastAPI 依赖注入用 ────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖：注入 AsyncSession。

    用法：
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── 生命周期用 ───────────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    应用启动时调用：
    1. 验证数据库可达性
    2. 若 system_settings 行不存在则初始化（首次部署）
    实际表结构由 Alembic 管理，不在此处 create_all。
    """
    import sqlalchemy

    async with engine.connect() as conn:
        await conn.execute(sqlalchemy.text("SELECT 1"))

    await _init_system_settings()
    await _init_default_pools()


async def _init_system_settings() -> None:
    """首次启动时写入 system_settings 单例行（id=1）。"""
    from app.core.config import settings as app_settings
    from app.core.security import hash_password
    from app.models.system_settings import SystemSettings

    async with AsyncSessionLocal() as session:
        row = await session.get(SystemSettings, 1)
        if row is None:
            row = SystemSettings(
                id=1,
                admin_password_hash=hash_password(app_settings.ADMIN_PASSWORD),
                token_version=1,
            )
            session.add(row)
            await session.commit()


async def _init_default_pools() -> None:
    """
    补齐内置默认变量池。

    行为约束：
    1. 仅创建缺失池
    2. 不覆盖管理员已维护的数据
    3. 可安全重复执行
    """
    from app.services.pool_service import PoolService

    async with AsyncSessionLocal() as session:
        seeded = await PoolService().seed_default_pools(session)
        if seeded.created > 0:
            await session.commit()
            logger.info("已补齐内置变量池 %s 个", seeded.created)


async def close_db() -> None:
    """应用关闭时释放连接池。"""
    await engine.dispose()
