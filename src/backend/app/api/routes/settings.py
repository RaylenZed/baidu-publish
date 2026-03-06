"""
系统设置路由（PRD §11.8 / PRD §6.6）

  GET  /settings           获取全部配置（不含密码哈希和 token_version）
  PUT  /settings           更新运行参数
  PUT  /settings/password  修改管理员密码（使所有已签发 token 失效）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse
from app.schemas.category import (
    CategoryResponse,
    CreateCategoryRequest,
    UpdateCategoryRequest,
)
from app.schemas.settings import (
    ChangePasswordRequest,
    SettingsResponse,
    UpdateSettingsRequest,
)
from app.services.category_service import CategoryService
from app.services.settings_service import SettingsService

router = APIRouter()
_svc = SettingsService()
_category_svc = CategoryService()


@router.get(
    "/categories",
    summary="获取系统支持的品类列表",
    response_model=ApiResponse[list[str]],
)
async def get_categories(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[str]]:
    """返回当前启用品类列表，供前端下拉/多选使用。"""
    return ApiResponse.ok(await _category_svc.list_category_names(db, enabled_only=True))


@router.get(
    "/categories/manage",
    summary="获取全部品类（含停用）",
    response_model=ApiResponse[list[CategoryResponse]],
)
async def list_categories_manage(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CategoryResponse]]:
    rows = await _category_svc.list_categories(db)
    return ApiResponse.ok([CategoryResponse.model_validate(row) for row in rows])


@router.post(
    "/categories",
    summary="新增品类",
    response_model=ApiResponse[CategoryResponse],
)
async def create_category(
    body: CreateCategoryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CategoryResponse]:
    """
    新增品类。

    行为：
    - 新品类会自动补齐一套 starter angle/persona 变量池
    - 后续可在变量池页继续扩充与细化
    """
    row = await _category_svc.create_category(db, body)
    await db.commit()
    return ApiResponse.ok(CategoryResponse.model_validate(row))


@router.put(
    "/categories/{category_id}",
    summary="更新品类",
    response_model=ApiResponse[CategoryResponse],
)
async def update_category(
    category_id: int,
    body: UpdateCategoryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CategoryResponse]:
    """
    更新品类名称 / 启停 / 排序。

    - 若修改名称，会同步更新账号、任务、变量池与历史审计中的品类字符串
    """
    row = await _category_svc.update_category(db, category_id, body)
    await db.commit()
    return ApiResponse.ok(CategoryResponse.model_validate(row))


@router.delete(
    "/categories/{category_id}",
    summary="删除未被使用的品类",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_category(
    category_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _category_svc.delete_category(db, category_id)
    await db.commit()


@router.get(
    "",
    summary="获取全部系统配置",
    response_model=ApiResponse[SettingsResponse],
)
async def get_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SettingsResponse]:
    """返回全局运行参数与通知配置（不含 admin_password_hash、token_version）。"""
    row = await _svc.get_settings(db)
    return ApiResponse.ok(SettingsResponse.model_validate(row))


@router.put(
    "",
    summary="更新系统配置",
    response_model=ApiResponse[SettingsResponse],
)
async def update_settings(
    body: UpdateSettingsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SettingsResponse]:
    """
    批量更新系统运行参数，所有字段可选，仅传入需修改的字段。

    约束：
    - account_delay: 1..300 秒（账号间执行间隔）
    - max_concurrent_accounts: 1..3（CLAUDE.md §3 #2）
    - task_timeout_minutes: 10..600 分钟（任务总超时兜底）
    - wecom_webhook: 传空字符串即清除 Webhook 配置
    """
    row = await _svc.update_settings(db, body)
    await db.commit()
    return ApiResponse.ok(SettingsResponse.model_validate(row))


@router.put(
    "/password",
    summary="修改管理员密码（使所有已签发 token 失效）",
    response_model=ApiResponse[None],
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """
    修改管理员密码。

    - 验证 old_password 正确
    - 新密码 bcrypt 加密后存储
    - token_version += 1：所有已签发 JWT（含当前 token）立即失效，需重新登录
    """
    await _svc.change_password(db, body.old_password, body.new_password)
    await db.commit()
    return ApiResponse.empty()
