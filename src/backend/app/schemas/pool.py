"""
变量池 Pydantic Schema（请求体 + 响应体）。

POOL-01  读取池内容
POOL-02  更新池（至少保留 1 个 enabled 项）
POOL-03  角度/人设为品类专属，其余 4 个为通用池
POOL-04  7 天去重（软规则，超过尝试次数后放行）
POOL-05  combo_id 格式：A{angle}P{persona}S{style}T{title_style}
POOL-06  combo_history 记录每次使用
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.core.constants import PoolType


# ── 通用子模型 ─────────────────────────────────────────────────────────────


class PoolItem(BaseModel):
    value: str = Field(min_length=1, description="条目文本")
    weight: int = Field(default=1, ge=1, le=100, description="抽取权重，1..100")
    enabled: bool = Field(default=True, description="是否参与随机抽取")


# ── 请求体 ─────────────────────────────────────────────────────────────────


class UpdatePoolRequest(BaseModel):
    category: str | None = Field(
        None,
        description="品类名（角度/人设池必须提供；通用池忽略此字段）",
    )
    items: Annotated[list[PoolItem], Field(min_length=1, description="池项目列表")]

    @field_validator("items")
    @classmethod
    def at_least_one_enabled(cls, v: list[PoolItem]) -> list[PoolItem]:
        if not any(item.enabled for item in v):
            raise ValueError("至少需要保留 1 个 enabled=true 的条目（POOL-03）")
        return v


# ── 响应体 ─────────────────────────────────────────────────────────────────


class PoolResponse(BaseModel):
    id: int
    pool_type: PoolType
    category: str | None
    items: list[PoolItem]
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComboHistoryResponse(BaseModel):
    id: int
    account_id: int
    category: str
    combo_id: str
    task_id: int | None
    used_at: datetime

    model_config = {"from_attributes": True}


class SeedPoolsResponse(BaseModel):
    created: int = Field(ge=0, description="本次新增的默认池数量")
    skipped: int = Field(ge=0, description="已存在而跳过的池数量")
    total_defaults: int = Field(ge=0, description="内置默认池总数量")


# ── 内部数据类（sample_combo 返回值）────────────────────────────────────────


class ComboResult(BaseModel):
    """变量池抽样结果，供 TaskService 使用。"""
    combo_id: str
    angle: str
    persona: str
    style: str
    structure: str
    title_style: str
    time_hook: str
    # 各维度 1-based 序号（用于 combo_id 构成）
    angle_idx: int
    persona_idx: int
    style_idx: int
    title_style_idx: int
