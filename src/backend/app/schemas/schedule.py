"""
定时任务 Pydantic DTO（PRD §6.3.5 / §11.6）
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import TaskMode


class ScheduleResponse(BaseModel):
    """定时任务详情响应。"""
    id: int
    name: str
    cron_expr: str
    mode: TaskMode
    timezone: str
    enabled: bool
    last_fired_at: datetime | None
    next_fire_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScheduleAccountResponse(BaseModel):
    """关联账号响应。"""
    account_id: int
    account_name: str

    model_config = {"from_attributes": True}


class ScheduleDetailResponse(ScheduleResponse):
    """定时任务详情（含关联账号列表）。"""
    accounts: list[ScheduleAccountResponse] = []

    model_config = {"from_attributes": True}


class ScheduleCreateRequest(BaseModel):
    """创建定时任务请求。"""
    name: str = Field(..., min_length=1, max_length=50)
    cron_expr: str = Field(..., min_length=9, max_length=30)
    mode: TaskMode
    timezone: str = Field(default="Asia/Shanghai")
    account_ids: list[int] = Field(..., min_length=1)
    topic_keyword: str | None = Field(default=None, max_length=50)
    product_name: str | None = Field(default=None, max_length=50)


class ScheduleUpdateRequest(BaseModel):
    """编辑定时任务请求。"""
    name: str | None = Field(default=None, min_length=1, max_length=50)
    cron_expr: str | None = Field(default=None, min_length=9, max_length=30)
    mode: TaskMode | None = None
    timezone: str | None = Field(default=None, max_length=30)
    account_ids: list[int] | None = Field(default=None, min_length=1)
    topic_keyword: str | None = Field(default=None, max_length=50)
    product_name: str | None = Field(default=None, max_length=50)