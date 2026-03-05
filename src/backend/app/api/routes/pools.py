"""
变量池路由（PRD §11.7 / PRD §6.5）

路由注意：静态路径（/combo-history）必须在动态路径（/{pool_type}）之前注册。

  GET  /pools                       全部变量池（所有类型 + 品类专属）
  GET  /pools/combo-history         最近 N 天的组合使用历史
  GET  /pools/{pool_type}           指定类型的池（可按品类过滤）
  PUT  /pools/{pool_type}           更新池内容（首次调用即自动创建）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse
from app.core.constants import PoolType
from app.core.exceptions import ValidationException
from app.schemas.pool import (
    ComboHistoryResponse,
    PoolResponse,
    UpdatePoolRequest,
)
from app.services.pool_service import PoolService

router = APIRouter()
_svc = PoolService()


# ── 静态路径（必须在动态路径前注册） ─────────────────────────────────────────

@router.get(
    "",
    summary="获取全部变量池",
    response_model=ApiResponse[list[PoolResponse]],
)
async def list_pools(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[PoolResponse]]:
    """返回系统中已配置的所有变量池（按 pool_type, category 排序）。"""
    pools = await _svc.list_pools(db)
    return ApiResponse.ok([PoolResponse.model_validate(p) for p in pools])


@router.get(
    "/combo-history",
    summary="组合使用历史（最近 N 天）",
    response_model=ApiResponse[list[ComboHistoryResponse]],
)
async def get_combo_history(
    account_id: int | None = Query(None, description="按账号 ID 过滤"),
    category: str | None = Query(None, description="按品类过滤"),
    days: int = Query(7, ge=1, le=90, description="查询最近几天，默认 7 天"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ComboHistoryResponse]]:
    """查询近 N 天内的组合使用历史，可按账号 ID 或品类过滤。"""
    history = await _svc.get_combo_history(db, account_id, category, days)
    return ApiResponse.ok([ComboHistoryResponse.model_validate(h) for h in history])


# ── 动态路径 ──────────────────────────────────────────────────────────────────

@router.get(
    "/{pool_type}",
    summary="获取指定类型变量池",
    response_model=ApiResponse[PoolResponse],
)
async def get_pool(
    pool_type: PoolType,
    category: str | None = Query(None, description="品类名（角度/人设池必须提供）"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PoolResponse]:
    """
    获取指定类型的变量池。
    - 角度（angle）、人设（persona）：须传 category 参数
    - 其余 4 个通用池：category 可省略
    """
    pool = await _svc.get_pool(db, pool_type, _resolve_category(pool_type, category))
    return ApiResponse.ok(PoolResponse.model_validate(pool))


@router.put(
    "/{pool_type}",
    summary="更新变量池内容（首次调用即自动创建）",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[PoolResponse],
)
async def update_pool(
    pool_type: PoolType,
    body: UpdatePoolRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PoolResponse]:
    """
    更新（或首次创建）变量池。

    约束：
    - 角度/人设池（品类专属）：body.category 必须提供且须在系统品类列表中
    - 通用池：body.category 被忽略（强制存 NULL）
    - items 中至少保留 1 个 enabled=true 的条目（POOL-03）
    """
    pool = await _svc.update_pool(db, pool_type, body)
    await db.commit()
    return ApiResponse.ok(PoolResponse.model_validate(pool))


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _resolve_category(pool_type: PoolType, category: str | None) -> str | None:
    """品类专属池强制要求 category，通用池强制 None。"""
    from app.services.pool_service import CATEGORY_POOL_TYPES
    if pool_type in CATEGORY_POOL_TYPES and not category:
        raise ValidationException(f"{pool_type.value} 是品类专属池，请通过 ?category= 指定品类")
    if pool_type not in CATEGORY_POOL_TYPES:
        return None
    return category
