"""
系统设置 Pydantic Schema（请求体 + 响应体）。

SET-01  account_delay: 1..300 秒
SET-02  max_concurrent_accounts: 1..3（CLAUDE.md §3 #2）
SET-03  task_timeout_minutes: 10..600 分钟（CLAUDE.md §4.5）
SET-04  步骤超时均为正整数秒
SET-05  修改密码 new_password 最短 8 字符
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import AigcModel, NotifyLevel, TaskMode


# ── 请求体 ─────────────────────────────────────────────────────────────────


class UpdateSettingsRequest(BaseModel):
    run_mode: TaskMode | None = None
    aigc_model: AigcModel | None = None
    account_delay: int | None = Field(None, ge=1, le=300, description="账号间延迟（秒），1..300")
    max_concurrent_accounts: int | None = Field(None, ge=1, le=3, description="跨账号并发数，1..3")
    daily_limit: int | None = Field(None, ge=1, le=100, description="单账号每日最大执行次数")
    task_timeout_minutes: int | None = Field(None, ge=10, le=600, description="总超时（分钟），10..600")
    generate_timeout: int | None = Field(None, ge=30, le=600, description="AI 生成步骤超时（秒），30..600")
    polish_timeout: int | None = Field(None, ge=30, le=600, description="AI 润色步骤超时（秒），30..600")
    cover_timeout: int | None = Field(None, ge=10, le=300, description="封面搜索超时（秒），10..300")
    publish_timeout: int | None = Field(None, ge=10, le=300, description="发布步骤超时（秒），10..300")
    draft_timeout: int | None = Field(None, ge=10, le=300, description="草稿保存超时（秒），10..300")
    wecom_webhook: str | None = Field(None, description="企微 Webhook URL，传空字符串即清除")
    notify_level: NotifyLevel | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, description="当前密码")
    new_password: str = Field(min_length=8, description="新密码，至少 8 位")


# ── 响应体 ─────────────────────────────────────────────────────────────────


class SettingsResponse(BaseModel):
    id: int
    run_mode: TaskMode
    aigc_model: AigcModel
    account_delay: int
    max_concurrent_accounts: int
    daily_limit: int
    task_timeout_minutes: int
    generate_timeout: int
    polish_timeout: int
    cover_timeout: int
    publish_timeout: int
    draft_timeout: int
    wecom_webhook: str | None
    notify_level: NotifyLevel
    updated_at: datetime

    model_config = {"from_attributes": True}
