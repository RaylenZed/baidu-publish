"""
仪表盘路由（PRD §11.2 / PRD §6.1）

  GET /api/v1/dashboard/stats          今日统计卡片
  GET /api/v1/dashboard/recent-tasks   最近任务流水
  GET /api/v1/dashboard/account-health 账号健康度列表
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse
from app.core.constants import CookieStatus, TaskStatus
from app.models.account import Account
from app.models.task import Task

router = APIRouter()


@router.get(
    "/stats",
    summary="今日统计（成功/失败/待执行/总耗时）",
    response_model=ApiResponse[dict],
)
async def get_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    聚合今日任务统计：
      - success_count: 成功数
      - failed_count: 失败数
      - running_count: 运行中数
      - pending_count: 待执行数
      - total_duration: 总耗时（秒，仅成功任务）
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 按状态计数
    status_counts = {}
    for status in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.RUNNING, TaskStatus.PENDING]:
        stmt = select(func.count()).select_from(Task).where(
            Task.created_at >= today_start,
            Task.status == status,
        )
        count = (await db.execute(stmt)).scalar_one()
        status_counts[status.value] = count

    # 成功任务的总耗时
    stmt_duration = select(func.sum(
        func.extract('epoch', Task.finished_at) - func.extract('epoch', Task.started_at)
    )).select_from(Task).where(
        Task.created_at >= today_start,
        Task.status == TaskStatus.SUCCESS,
        Task.finished_at.isnot(None),
        Task.started_at.isnot(None),
    )
    total_duration = (await db.execute(stmt_duration)).scalar_one() or 0

    return ApiResponse.ok({
        "success_count": status_counts.get(TaskStatus.SUCCESS.value, 0),
        "failed_count": status_counts.get(TaskStatus.FAILED.value, 0),
        "running_count": status_counts.get(TaskStatus.RUNNING.value, 0),
        "pending_count": status_counts.get(TaskStatus.PENDING.value, 0),
        "total_duration_seconds": int(total_duration),
    })


@router.get(
    "/recent-tasks",
    summary="最近任务流水",
    response_model=ApiResponse[list[dict]],
)
async def get_recent_tasks(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict]]:
    """查询最近 N 条任务（含账号名、状态、执行时间）。"""
    from app.models.account import Account

    stmt = (
        select(Task, Account.name)
        .join(Account, Task.account_id == Account.id)
        .order_by(Task.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for task, account_name in rows:
        items.append({
            "id": task.id,
            "account_id": task.account_id,
            "account_name": account_name,
            "category": task.category,
            "mode": task.mode,
            "status": task.status,
            "warning": task.warning,
            "error_type": task.error_type,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        })

    return ApiResponse.ok(items)


@router.get(
    "/account-health",
    summary="账号 Cookie 健康度",
    response_model=ApiResponse[list[dict]],
)
async def get_account_health(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict]]:
    """查询所有账号的 Cookie 状态及上次检查时间。"""
    stmt = select(
        Account.id,
        Account.name,
        Account.cookie_status,
        Account.cookie_checked_at,
    ).order_by(Account.id)
    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for account_id, name, status, checked_at in rows:
        items.append({
            "account_id": account_id,
            "account_name": name,
            "cookie_status": status,
            "cookie_checked_at": checked_at.isoformat() if checked_at else None,
        })

    return ApiResponse.ok(items)