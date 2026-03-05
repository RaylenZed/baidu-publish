"""
统一 API 响应体（CLAUDE.md §4.2）。

成功响应：
    { "success": true, "data": <T> }

错误响应（由全局 exception_handler 返回，路由层不直接构造）：
    { "success": false, "errorCode": "TASK_NOT_FOUND", "message": "...",
      "requestId": "abc", "details": {} }

分页数据嵌入 data 字段：
    { "success": true, "data": { "items": [...], "total": 100, "page": 1,
                                  "size": 20, "pages": 5 } }

使用方式：
    return ApiResponse.ok(data)
    return ApiResponse.ok(PageData.of(items, total, page, size))
    return ApiResponse.empty()          # 无返回体的操作（DELETE/PUT）
"""

from __future__ import annotations

import math
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ── 分页数据容器 ──────────────────────────────────────────────────────────────

class PageData(BaseModel, Generic[T]):
    """嵌入 ApiResponse.data 的分页结构。"""

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    size: int = Field(ge=1)
    pages: int = Field(ge=0)

    @classmethod
    def of(
        cls,
        items: list[T],
        total: int,
        page: int,
        size: int,
    ) -> "PageData[T]":
        pages = math.ceil(total / size) if size > 0 else 0
        return cls(items=items, total=total, page=page, size=size, pages=pages)


# ── 成功响应 ─────────────────────────────────────────────────────────────────

class ApiResponse(BaseModel, Generic[T]):
    """
    所有路由的成功响应体。

    路由直接 return ApiResponse.ok(data) 即可，FastAPI 自动序列化。
    """

    success: bool = True
    data: T | None = None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        """有业务数据的成功响应。"""
        return cls(success=True, data=data)

    @classmethod
    def empty(cls) -> "ApiResponse[None]":
        """无返回体的操作（删除、更新等）。"""
        return cls(success=True, data=None)


# ── 错误响应（仅供全局 exception_handler 使用）────────────────────────────────

class ErrorResponse(BaseModel):
    """
    全局异常处理器构造的错误响应。
    路由层不应直接实例化此类，抛出 AppException 子类即可。
    """

    success: bool = False
    errorCode: str
    message: str
    requestId: str = ""
    details: dict[str, Any] = {}


# ── 分页请求参数（复用，方便 Query 注入）─────────────────────────────────────

class PaginationParams(BaseModel):
    """统一分页请求参数，通过 Depends(PaginationParams) 注入。"""

    page: int = Field(1, ge=1, description="页码，从 1 开始")
    size: int = Field(20, ge=1, le=100, description="每页条数，最大 100")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size
