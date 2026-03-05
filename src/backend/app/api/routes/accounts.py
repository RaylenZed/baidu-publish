"""
账号管理路由（PRD §11.3 / PRD §6.2）

路由注意：静态路径（/export、/check-all）必须在动态路径（/{account_id}）之前注册，
否则 FastAPI 会将 "export" 误解析为 account_id。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse, PageData
from app.schemas.account import (
    AccountResponse,
    CheckAllResult,
    CookieCheckResult,
    CreateAccountRequest,
    ExportRequest,
    ExportResponse,
    ImportRequest,
    ImportResult,
    UpdateAccountRequest,
)
from app.services.account_service import AccountService

router = APIRouter()
_svc = AccountService()


# ── 静态路径（必须在动态路径前注册） ─────────────────────────────────────────

@router.post(
    "/export",
    summary="导出账号配置（口令加密）",
    response_model=ApiResponse[ExportResponse],
)
async def export_accounts(
    body: ExportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ExportResponse]:
    """
    导出全部账号为加密二进制文件（base64 编码）。
    加密算法：PBKDF2-HMAC-SHA256（100000 轮）派生密钥 + AES-256-GCM。
    导出数据含明文 Cookie，请妥善保管口令。

    注：PRD 原始 spec 为 GET，此处改为 POST 以避免口令出现在 URL/日志中。
    """
    result = await _svc.export_accounts(db, body.passphrase)
    return ApiResponse.ok(result)


@router.post(
    "/import",
    summary="批量导入账号配置",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ImportResult],
)
async def import_accounts(
    body: ImportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ImportResult]:
    """
    解密并批量 upsert 账号。
    同名账号（name 相同）以导入数据覆盖 Cookie/品类，不修改检测状态。
    """
    result = await _svc.import_accounts(db, body.data, body.passphrase)
    await db.commit()
    return ApiResponse.ok(result)


@router.post(
    "/check-all",
    summary="批量检测所有账号 Cookie",
    response_model=ApiResponse[CheckAllResult],
)
async def check_all_cookies(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CheckAllResult]:
    """顺序检测全部账号，单个失败不影响其他账号。"""
    result = await _svc.check_all_cookies(db)
    await db.commit()
    return ApiResponse.ok(result)


# ── 列表 / 创建 ──────────────────────────────────────────────────────────────

@router.get(
    "",
    summary="账号列表（分页）",
    response_model=ApiResponse[PageData[AccountResponse]],
)
async def list_accounts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PageData[AccountResponse]]:
    """返回账号分页列表（Cookie 脱敏，只展示 BDUSS 末 6 位）。"""
    accounts, total = await _svc.list_accounts(db, page=page, size=size, keyword=keyword)
    items = [AccountResponse(**_svc.to_response(a)) for a in accounts]
    return ApiResponse.ok(PageData.of(items, total, page, size))


@router.post(
    "",
    summary="新增账号",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AccountResponse],
)
async def create_account(
    body: CreateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AccountResponse]:
    """
    新增账号。校验规则：
    - name 1-50 字符且全局唯一（ACC-02）
    - cookie 必须含 BDUSS=（ACC-03）
    - categories 1-2 个，来自系统品类枚举（ACC-01）
    """
    account = await _svc.create_account(db, body)
    await db.commit()
    return ApiResponse.ok(AccountResponse(**_svc.to_response(account)))


# ── 动态路径 ──────────────────────────────────────────────────────────────────

@router.get(
    "/{account_id}",
    summary="获取单个账号",
    response_model=ApiResponse[AccountResponse],
)
async def get_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AccountResponse]:
    """按 ID 获取单个账号详情。"""
    account = await _svc.get_account(db, account_id)
    return ApiResponse.ok(AccountResponse(**_svc.to_response(account)))


@router.post(
    "/{account_id}/check-cookie",
    summary="检测单个账号 Cookie",
    response_model=ApiResponse[CookieCheckResult],
)
async def check_cookie(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CookieCheckResult]:
    """
    调用百家号 refresh_token 接口验证 Cookie 有效性。
    - 成功 → cookie_status=active
    - 失败 → cookie_status=expired
    """
    result = await _svc.check_cookie(db, account_id)
    await db.commit()
    return ApiResponse.ok(result)


@router.put(
    "/{account_id}",
    summary="编辑账号",
    response_model=ApiResponse[AccountResponse],
)
async def update_account(
    account_id: int,
    body: UpdateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AccountResponse]:
    """更新账号信息。更新 Cookie 会自动将 cookie_status 重置为 unchecked。"""
    account = await _svc.update_account(db, account_id, body)
    await db.commit()
    return ApiResponse.ok(AccountResponse(**_svc.to_response(account)))


@router.delete(
    "/{account_id}",
    summary="删除账号",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    删除账号（ACC-05）：有 pending/running 任务时返回 400 错误，
    需先取消或等待任务完成。
    """
    await _svc.delete_account(db, account_id)
    await db.commit()
