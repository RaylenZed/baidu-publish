"""
任务管理 Pydantic Schema（请求体 + 响应体）。

TASK-01  创建任务（含幂等、防重、限额检查）
TASK-04  状态机：pending → running → success/failed/timeout；pending → canceled
TASK-05  重试：创建新任务，retry_of_task_id 追踪链路
TASK-07  idempotency_key 5 分钟去重（Redis + DB 兜底）
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.core.constants import (
    CATEGORIES,
    LogLevel,
    TaskErrorType,
    TaskMode,
    TaskStatus,
    TaskStep,
    TaskWarning,
)


# ── 请求体 ─────────────────────────────────────────────────────────────────


class CreateTaskRequest(BaseModel):
    account_ids: Annotated[
        list[int],
        Field(min_length=1, max_length=10, description="账号 ID 列表，批量创建（1-10 个账号）"),
    ]
    category: str | None = Field(None, description="品类名，留空则随机选择账号绑定的品类")
    mode: TaskMode = Field(default=TaskMode.PUBLISH, description="执行模式：draft / publish")
    topic_keyword: str | None = Field(None, max_length=50, description="主题关键词（可选）")
    product_name: str | None = Field(None, max_length=50, description="产品/品牌名（可选）")
    idempotency_key: str | None = Field(
        None, max_length=100,
        description="幂等 key（UUID），5 分钟内相同 key 返回已有任务",
    )

    @field_validator("category")
    @classmethod
    def category_must_be_valid(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None  # 留空则随机选择
        if v not in CATEGORIES:
            raise ValueError(f"品类「{v}」不在系统品类列表中")
        return v


# ── 响应体 ─────────────────────────────────────────────────────────────────


class TaskResponse(BaseModel):
    id: int
    account_id: int
    account_name: str | None = None   # JOIN 填充，不在 ORM 对象上
    schedule_id: int | None
    retry_of_task_id: int | None
    category: str
    mode: TaskMode
    status: TaskStatus
    error_type: TaskErrorType | None
    warning: TaskWarning | None
    combo_id: str | None
    topic_keyword: str | None
    product_name: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    timeout_at: datetime | None
    last_step_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BatchCreateResult(BaseModel):
    """批量创建任务的返回结果（多账号场景）。"""
    created: list[TaskResponse] = Field(default_factory=list)
    errors: list[dict] = Field(
        default_factory=list,
        description="创建失败的条目：[{account_id, errorCode, message}]",
    )


class TaskLogResponse(BaseModel):
    id: int
    task_id: int
    step: TaskStep
    level: LogLevel
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}
