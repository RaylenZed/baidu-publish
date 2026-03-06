"""
品类管理 DTO。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CreateCategoryRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=20, description="品类名称")
    enabled: bool = Field(default=True, description="是否启用")
    sort_order: int | None = Field(
        default=None,
        ge=0,
        le=999,
        description="排序值，留空时自动排到最后",
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("品类名称不能为空")
        return normalized


class UpdateCategoryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=20)
    enabled: bool | None = Field(default=None)
    sort_order: int | None = Field(default=None, ge=0, le=999)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("品类名称不能为空")
        return normalized


class CategoryResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
