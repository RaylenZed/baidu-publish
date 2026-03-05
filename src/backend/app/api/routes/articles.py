"""
文章管理路由（PRD §11.5 / PRD §6.4）

  GET    /articles                      文章列表（分页+筛选）
  GET    /articles/{id}                 文章详情（含初稿/润色对比）
  PUT    /articles/{id}                 在线编辑（仅 draft 状态）
  POST   /articles/{id}/confirm         人工确认清除 content_warning
  POST   /articles/{id}/publish         手动发布草稿到百家号
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse, PageData
from app.core.constants import ContentWarning, PublishStatus
from app.core.security import decrypt_cookie
from app.schemas.article import ArticleResponse, ArticleUpdateRequest
from app.services.article_service import ArticleService

router = APIRouter()
_svc = ArticleService()


@router.get(
    "",
    summary="文章列表（分页 + 多维筛选）",
    response_model=ApiResponse[PageData[ArticleResponse]],
)
async def list_articles(
    account_id: int | None = Query(None, description="按账号 ID 筛选"),
    publish_status: PublishStatus | None = Query(None, description="按发布状态筛选"),
    content_warning: ContentWarning | None = Query(None, description="按内容风控标记筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PageData[ArticleResponse]]:
    items, total = await _svc.list_articles(
        db,
        account_id=account_id,
        publish_status=publish_status,
        content_warning=content_warning,
        page=page,
        size=size,
    )
    return ApiResponse.ok(
        PageData.of([ArticleResponse.model_validate(a) for a in items], total, page, size)
    )


@router.get(
    "/{article_id}",
    summary="文章详情（含初稿/润色对比）",
    response_model=ApiResponse[ArticleResponse],
)
async def get_article(
    article_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ArticleResponse]:
    article = await _svc.get_article(db, article_id)
    return ApiResponse.ok(ArticleResponse.model_validate(article))


@router.put(
    "/{article_id}",
    summary="在线编辑文章（仅 draft 状态）",
    response_model=ApiResponse[ArticleResponse],
)
async def update_article(
    article_id: int,
    body: ArticleUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ArticleResponse]:
    article = await _svc.update_article(db, article_id, body.title, body.body_md)
    await db.commit()
    await db.refresh(article)
    return ApiResponse.ok(ArticleResponse.model_validate(article))


@router.post(
    "/{article_id}/confirm",
    summary="人工确认清除 content_warning（允许后续发布）",
    response_model=ApiResponse[ArticleResponse],
)
async def confirm_article(
    article_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ArticleResponse]:
    """
    清除 partial_content 内容警告，使文章可以手动发布（PRD §10）。
    操作人需要在阅读并确认内容完整性后调用此接口。
    """
    article = await _svc.clear_content_warning(db, article_id)
    await db.commit()
    await db.refresh(article)
    return ApiResponse.ok(ArticleResponse.model_validate(article))


@router.post(
    "/{article_id}/publish",
    summary="手动发布草稿到百家号",
    response_model=ApiResponse[ArticleResponse],
)
async def publish_article(
    article_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ArticleResponse]:
    """
    手动触发文章发布：
      1. 检查文章状态（draft / publish_failed 才可发布）
      2. 检查 content_warning（partial_content 需先确认）
      3. 调用 BjhService 发布到百家号
    """
    # 获取关联账号的 cookie
    article = await _svc.get_article(db, article_id)
    from app.models.task import Task
    from app.models.account import Account
    task = await db.get(Task, article.task_id)
    account = await db.get(Account, task.account_id) if task else None
    if account is None:
        from app.core.exceptions import AppException
        raise AppException(
            code="ACCOUNT_NOT_FOUND",
            message="关联账号不存在",
            status_code=404,
        )
    cookie = decrypt_cookie(account.cookie_encrypted)

    try:
        result = await _svc.manual_publish(db, article_id, cookie)
    except Exception:
        # 发布失败时，service 已将状态改为 publish_failed；
        # 这里先 commit 以保证失败状态落库，再重新抛出让全局处理器返回错误响应。
        # get_db 之后的 rollback 对已提交事务是空操作。
        await db.commit()
        raise
    await db.commit()
    await db.refresh(result)
    return ApiResponse.ok(ArticleResponse.model_validate(result))
