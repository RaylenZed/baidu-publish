"""
定时任务路由（PRD §11.6 / PRD §6.3.5）

  GET    /schedules          定时任务列表
  GET    /schedules/{id}     定时任务详情（含关联账号）
  POST   /schedules          创建定时任务
  PUT    /schedules/{id}     编辑定时任务
  DELETE /schedules/{id}     删除定时任务
  POST   /schedules/{id}/toggle  切换启用/禁用状态
  POST   /schedules/{id}/fire    手动触发（测试用）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.response import ApiResponse
from app.schemas.schedule import (
    ScheduleCreateRequest,
    ScheduleDetailResponse,
    ScheduleResponse,
    ScheduleUpdateRequest,
)
from app.services.schedule_service import ScheduleService

router = APIRouter()
_svc = ScheduleService()


@router.get(
    "",
    summary="定时任务列表",
    response_model=ApiResponse[list[ScheduleResponse]],
)
async def list_schedules(
    enabled: bool | None = Query(None, description="按启用状态筛选"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ScheduleResponse]]:
    schedules = await _svc.list_schedules(db, enabled=enabled)
    return ApiResponse.ok([ScheduleResponse.model_validate(s) for s in schedules])


@router.get(
    "/{schedule_id}",
    summary="定时任务详情（含关联账号）",
    response_model=ApiResponse[ScheduleDetailResponse],
)
async def get_schedule(
    schedule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleDetailResponse]:
    schedule, accounts = await _svc.get_schedule_detail(db, schedule_id)
    response = ScheduleDetailResponse(
        id=schedule.id,
        name=schedule.name,
        cron_expr=schedule.cron_expr,
        mode=schedule.mode,
        timezone=schedule.timezone,
        enabled=schedule.enabled,
        last_fired_at=schedule.last_fired_at,
        next_fire_at=schedule.next_fire_at,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
        accounts=[
            {"account_id": a["account_id"], "account_name": a["account_name"]}
            for a in accounts
        ],
    )
    return ApiResponse.ok(response)


@router.post(
    "",
    summary="创建定时任务",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ScheduleResponse],
)
async def create_schedule(
    body: ScheduleCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    schedule = await _svc.create_schedule(
        db,
        name=body.name,
        cron_expr=body.cron_expr,
        mode=body.mode,
        timezone=body.timezone,
        account_ids=body.account_ids,
        topic_keyword=body.topic_keyword,
        product_name=body.product_name,
    )
    await db.commit()
    await db.refresh(schedule)
    return ApiResponse.ok(ScheduleResponse.model_validate(schedule))


@router.put(
    "/{schedule_id}",
    summary="编辑定时任务",
    response_model=ApiResponse[ScheduleResponse],
)
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    schedule = await _svc.update_schedule(
        db,
        schedule_id=schedule_id,
        name=body.name,
        cron_expr=body.cron_expr,
        mode=body.mode,
        timezone=body.timezone,
        account_ids=body.account_ids,
        topic_keyword=body.topic_keyword,
        product_name=body.product_name,
    )
    await db.commit()
    await db.refresh(schedule)
    return ApiResponse.ok(ScheduleResponse.model_validate(schedule))


@router.delete(
    "/{schedule_id}",
    summary="删除定时任务",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_schedule(
    schedule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _svc.delete_schedule(db, schedule_id)
    await db.commit()


@router.post(
    "/{schedule_id}/toggle",
    summary="切换启用/禁用状态",
    response_model=ApiResponse[ScheduleResponse],
)
async def toggle_schedule(
    schedule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    schedule = await _svc.toggle_schedule(db, schedule_id)
    await db.commit()
    await db.refresh(schedule)
    return ApiResponse.ok(ScheduleResponse.model_validate(schedule))


@router.post(
    "/{schedule_id}/fire",
    summary="手动触发定时任务（测试用）",
    response_model=ApiResponse[dict],
)
async def fire_schedule(
    schedule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """手动触发定时任务，立即为关联账号创建任务（不等待 cron 表达式）。"""
    tasks = await _svc.fire(db, schedule_id)
    await db.commit()
    return ApiResponse.ok({"created": len(tasks), "task_ids": [t.id for t in tasks]})