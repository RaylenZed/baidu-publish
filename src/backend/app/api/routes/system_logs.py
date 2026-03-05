"""
系统日志路由（PRD §11.8 / PRD §6.7）
  GET /settings/logs   系统运行日志（分页 + 筛选）

实现策略：
  - 业务日志：查询 task_logs 表，按 task_id/level/step/时间筛选
  - 与任务日志 API（/api/v1/tasks/{id}/logs）互补，此处侧重运维视角
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse, PageData
from app.core.constants import LogLevel, TaskStep
from app.models.task_log import TaskLog

router = APIRouter()


@router.get(
    "/logs",
    summary="系统日志查询（按级别/步骤/任务ID/时间筛选）",
    response_model=ApiResponse[PageData[dict]],
)
async def get_system_logs(
    level: Optional[LogLevel] = Query(None, description="日志级别筛选"),
    step: Optional[TaskStep] = Query(None, description="任务步骤筛选"),
    task_id: Optional[int] = Query(None, description="任务 ID 精确筛选"),
    date_from: Optional[datetime] = Query(None, description="起始时间"),
    date_to: Optional[datetime] = Query(None, description="结束时间"),
    keyword: Optional[str] = Query(None, description="关键词搜索（message 模糊匹配）"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PageData[dict]]:
    """
    查询系统日志（来源于 task_logs 表）。
    用于运维排查，聚合展示任务执行日志。
    """
    stmt = select(TaskLog)

    if task_id is not None:
        stmt = stmt.where(TaskLog.task_id == task_id)
    if level is not None:
        stmt = stmt.where(TaskLog.level == level)
    if step is not None:
        stmt = stmt.where(TaskLog.step == step)
    if date_from is not None:
        stmt = stmt.where(TaskLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(TaskLog.created_at <= date_to)
    if keyword:
        stmt = stmt.where(TaskLog.message.ilike(f"%{keyword}%"))

    # 总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # 分页
    stmt = stmt.order_by(TaskLog.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    items = [
        {
            "id": log.id,
            "task_id": log.task_id,
            "step": log.step,
            "level": log.level,
            "message": log.message,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]

    return ApiResponse.ok(PageData.of(items, total, page, size))