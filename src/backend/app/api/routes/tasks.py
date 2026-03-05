"""
任务管理路由（PRD §11.4 / PRD §6.3）

路由注意：静态路径（/retry-failed、/publish-drafts）必须在动态路径（/{task_id}）之前注册。

  GET    /tasks                     任务列表（分页+筛选）
  POST   /tasks                     批量创建任务（支持多账号）
  POST   /tasks/retry-failed        批量重试所有失败任务
  POST   /tasks/publish-drafts      发布所有草稿（占位，待 Module 9 实现）
  GET    /tasks/{task_id}           任务详情
  GET    /tasks/{task_id}/logs      任务历史日志（非实时）
  POST   /tasks/{task_id}/retry     重试失败/超时任务
  POST   /tasks/{task_id}/cancel    取消排队中任务
  POST   /tasks/{task_id}/force-draft  强制转草稿模式重跑

WebSocket 实时日志流见 app/ws/task_log_stream.py，路径 /ws/tasks/{id}/logs
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse, PageData
from app.core.constants import TaskMode, TaskStatus
from app.core.exceptions import AppException
from app.schemas.task import (
    BatchCreateResult,
    CreateTaskRequest,
    TaskLogResponse,
    TaskResponse,
)
from app.services.task_service import TaskService

router = APIRouter()
_svc = TaskService()


# ── 静态路径（必须在动态路径前注册） ─────────────────────────────────────────

@router.post(
    "/retry-failed",
    summary="批量重试所有失败/超时任务",
    response_model=ApiResponse[list[TaskResponse]],
)
async def retry_all_failed(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[TaskResponse]]:
    """为所有 failed / timeout 状态的任务各创建一个新的重试任务。"""
    created = await _svc.retry_all_failed(db)
    await db.commit()
    return ApiResponse.ok([TaskResponse.model_validate(t) for t in created])


@router.post(
    "/publish-drafts",
    summary="发布所有草稿文章",
    response_model=ApiResponse[dict],
)
async def publish_all_drafts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    触发所有待发布草稿文章（publish_status=draft 且 content_warning=NULL）的发布流程。
    遍历每个草稿，通过 article_service.manual_publish 发布。
    """
    from sqlalchemy import select
    from app.models.article import Article
    from app.models.task import Task
    from app.models.account import Account
    from app.core.constants import PublishStatus
    from app.core.security import decrypt_cookie
    from app.services.article_service import ArticleService

    # 查询所有可发布的草稿
    stmt = select(Article).join(Task).where(
        Article.publish_status == PublishStatus.DRAFT,
        Article.content_warning == None,  # noqa: E711
    )
    result = await db.execute(stmt)
    articles = result.scalars().all()

    if not articles:
        return ApiResponse.ok({"message": "没有可发布的草稿", "count": 0})

    article_svc = ArticleService()
    success_count = 0
    failed_count = 0

    for article in articles:
        try:
            task = await db.get(Task, article.task_id)
            if not task:
                continue
            account = await db.get(Account, task.account_id)
            if not account:
                continue

            cookie = decrypt_cookie(account.cookie_encrypted)
            try:
                await article_svc.manual_publish(db, article.id, cookie)
            except Exception:
                # 发布失败：先 commit 保留 publish_failed 状态，再计入失败数
                await db.commit()
                failed_count += 1
                continue
            await db.commit()
            success_count += 1
        except Exception:
            await db.rollback()
            failed_count += 1

    return ApiResponse.ok({
        "message": f"发布完成，成功 {success_count} 篇，失败 {failed_count} 篇",
        "success_count": success_count,
        "failed_count": failed_count,
    })


# ── 列表 / 创建 ────────────────────────────────────────────────────────────

@router.get(
    "",
    summary="任务列表（分页 + 多维筛选）",
    response_model=ApiResponse[PageData[TaskResponse]],
)
async def list_tasks(
    task_status: TaskStatus | None = Query(None, alias="status", description="按状态筛选"),
    account_id: int | None = Query(None, description="按账号 ID 筛选"),
    category: str | None = Query(None, description="按品类筛选"),
    mode: TaskMode | None = Query(None, description="按模式筛选：draft / publish"),
    date_from: datetime | None = Query(None, description="创建时间起（ISO-8601）"),
    date_to: datetime | None = Query(None, description="创建时间止（ISO-8601）"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PageData[TaskResponse]]:
    """多维筛选任务列表，支持按状态、账号、品类、模式、时间范围过滤，带分页。"""
    items, total = await _svc.list_tasks(
        db,
        status=task_status,
        account_id=account_id,
        category=category,
        mode=mode,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    # 批量查账号名，避免 N+1
    from sqlalchemy import select as sa_select
    from app.models.account import Account as AccountModel
    acc_ids = {t.account_id for t in items}
    acc_name_map: dict[int, str] = {}
    if acc_ids:
        rows = (await db.execute(
            sa_select(AccountModel.id, AccountModel.name).where(AccountModel.id.in_(acc_ids))
        )).all()
        acc_name_map = {row[0]: row[1] for row in rows}
    response_items = [
        TaskResponse.model_validate(t).model_copy(update={"account_name": acc_name_map.get(t.account_id)})
        for t in items
    ]
    return ApiResponse.ok(PageData.of(response_items, total, page, size))


@router.post(
    "",
    summary="批量创建任务（支持多账号）",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[BatchCreateResult],
)
async def create_tasks(
    body: CreateTaskRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[BatchCreateResult]:
    """
    为指定账号列表批量创建任务。

    - 每个账号独立校验（幂等 key 自动附加 account_id 后缀）
    - 单个账号创建失败不影响其他账号
    - 返回成功创建的任务列表 + 失败详情
    """
    result = BatchCreateResult()

    for account_id in body.account_ids:
        # 多账号时，为每个账号生成独立的幂等 key（避免相互冲突）
        per_account_key = (
            f"{body.idempotency_key}:{account_id}"
            if body.idempotency_key else None
        )
        try:
            task = await _svc.create_task(
                db,
                account_id=account_id,
                category=body.category,
                mode=body.mode,
                topic_keyword=body.topic_keyword,
                product_name=body.product_name,
                idempotency_key=per_account_key,
            )
            result.created.append(TaskResponse.model_validate(task))
        except AppException as exc:
            result.errors.append({
                "account_id": account_id,
                "errorCode": exc.code,
                "message": exc.message,
            })

    # 只要有创建成功的任务就 commit
    if result.created:
        await db.commit()

    return ApiResponse.ok(result)


# ── 动态路径 ──────────────────────────────────────────────────────────────────

@router.get(
    "/{task_id}",
    summary="任务详情",
    response_model=ApiResponse[TaskResponse],
)
async def get_task(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskResponse]:
    task = await _svc.get_task(db, task_id)
    return ApiResponse.ok(TaskResponse.model_validate(task))


@router.get(
    "/{task_id}/logs",
    summary="任务历史日志（非实时）",
    response_model=ApiResponse[list[TaskLogResponse]],
)
async def get_task_logs(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[TaskLogResponse]]:
    """
    获取任务的所有历史日志（按时间升序）。
    实时日志流请使用 WebSocket：ws://.../ws/tasks/{task_id}/logs
    """
    logs = await _svc.get_task_logs(db, task_id)
    return ApiResponse.ok([TaskLogResponse.model_validate(l) for l in logs])


@router.post(
    "/{task_id}/retry",
    summary="重试失败/超时任务",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TaskResponse],
)
async def retry_task(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskResponse]:
    """
    为 failed / timeout 状态的任务创建重试任务（新 task_id）。
    原任务状态保持不变，通过 retry_of_task_id 追踪重试链路。
    """
    new_task = await _svc.retry_task(db, task_id)
    await db.commit()
    return ApiResponse.ok(TaskResponse.model_validate(new_task))


@router.post(
    "/{task_id}/cancel",
    summary="取消排队中任务",
    response_model=ApiResponse[TaskResponse],
)
async def cancel_task(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskResponse]:
    """取消 pending 状态的任务，已运行的任务无法取消。"""
    task = await _svc.cancel_task(db, task_id)
    await db.commit()
    return ApiResponse.ok(TaskResponse.model_validate(task))


@router.post(
    "/{task_id}/force-draft",
    summary="强制转草稿模式重跑",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TaskResponse],
)
async def force_draft_task(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskResponse]:
    """
    将 failed / timeout / running 任务强制以 draft 模式重跑。
    新建 mode=draft 的任务，跳过封面搜索和正式发布步骤，仅保存草稿。
    """
    new_task = await _svc.force_draft(db, task_id)
    await db.commit()
    return ApiResponse.ok(TaskResponse.model_validate(new_task))
