"""
账号管理 Pydantic Schema（请求体 + 响应体）。

ACC-01  categories 长度 1-2，值来自数据库启用品类列表
ACC-02  name 全局唯一（DB UNIQUE 约束兜底）
ACC-03  cookie 必须包含 BDUSS=
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.core.constants import CookieStatus

# ── 请求体 ─────────────────────────────────────────────────────────────────


class CreateAccountRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=50, description="账号名称，全局唯一")]
    cookie: str = Field(description="明文 Cookie，必须包含 BDUSS=")
    categories: Annotated[
        list[str],
        Field(min_length=1, max_length=2, description="绑定品类，1-2 个，来自系统品类枚举"),
    ]

    @field_validator("cookie")
    @classmethod
    def cookie_must_contain_bduss(cls, v: str) -> str:
        if "BDUSS=" not in v:
            raise ValueError("Cookie 必须包含 BDUSS= 字段（ACC-03）")
        return v

    @field_validator("categories")
    @classmethod
    def categories_must_be_distinct(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("品类不能重复")
        return v


class UpdateAccountRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    cookie: str | None = Field(None, description="明文 Cookie，更新时必须包含 BDUSS=")
    categories: list[str] | None = Field(None, min_length=1, max_length=2)

    @field_validator("cookie")
    @classmethod
    def cookie_must_contain_bduss(cls, v: str | None) -> str | None:
        if v is not None and "BDUSS=" not in v:
            raise ValueError("Cookie 必须包含 BDUSS= 字段（ACC-03）")
        return v

    @field_validator("categories")
    @classmethod
    def categories_must_be_distinct(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(set(v)) != len(v):
            raise ValueError("品类不能重复")
        return v


class ExportRequest(BaseModel):
    passphrase: str = Field(min_length=1, description="导出加密口令（PBKDF2+AES-256-GCM）")


class ImportRequest(BaseModel):
    data: str = Field(description="base64 编码的加密账号数据（由本系统导出）")
    passphrase: str = Field(min_length=1, description="解密口令")


# ── 响应体 ─────────────────────────────────────────────────────────────────


class AccountResponse(BaseModel):
    id: int
    name: str
    cookie_masked: str = Field(description="脱敏 Cookie，仅展示 BDUSS 末 6 位")
    categories: list[str]
    cookie_status: CookieStatus
    cookie_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CookieCheckResult(BaseModel):
    account_id: int
    name: str
    cookie_status: CookieStatus
    checked_at: datetime


class CheckAllResult(BaseModel):
    total: int
    active: int
    expired: int
    results: list[CookieCheckResult]


class ExportResponse(BaseModel):
    data: str = Field(description="base64 编码的加密导出数据")
    filename: str = "accounts_export.bin"
    count: int = Field(description="导出账号数量")


class ImportResult(BaseModel):
    created: int
    updated: int
    failed: int
    details: list[dict] = Field(default_factory=list, description="失败条目的原因")
