"""
system_settings 表：全局系统配置（单行，id 始终为 1）。

PRD §6.6 定义了大量系统设置项，但未在数据模型章节定义对应的持久化表。
此表为补充设计，采用 Singleton 模式（表中永远只有一行）。

包含：
  - 运行参数（模式、并发、限额、超时）
  - 通知配置（企微 Webhook、通知级别）
  - 认证信息（密码哈希、token_version）
    * token_version 用于实现"修改密码后所有 JWT 自动失效"（CLAUDE.md 安全基线）

使用方式：
  settings = await session.get(SystemSettings, 1)
  if settings is None:
      settings = SystemSettings(id=1, ...)  # 首次启动时 seed
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_values
from app.core.constants import (
    AigcModel,
    NotifyLevel,
    TaskMode,
    DEFAULT_ACCOUNT_DELAY,
    DEFAULT_AIGC_MODEL,
    DEFAULT_COVER_TIMEOUT,
    DEFAULT_DAILY_LIMIT,
    DEFAULT_DRAFT_TIMEOUT,
    DEFAULT_GENERATE_TIMEOUT,
    DEFAULT_MAX_CONCURRENT_ACCOUNTS,
    DEFAULT_POLISH_TIMEOUT,
    DEFAULT_PUBLISH_TIMEOUT,
    DEFAULT_TASK_TIMEOUT_MINUTES,
)


class SystemSettings(Base):
    """
    系统全局配置，单行 Singleton（id 固定为 1）。
    此表在 PRD 数据模型章节缺失，此处补充。
    """

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        comment="固定为 1（Singleton）",
    )

    # ── 运行参数 ─────────────────────────────────────────────────────────────

    run_mode: Mapped[TaskMode] = mapped_column(
        SAEnum(
            TaskMode,
            name="task_mode_enum",
            create_type=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=TaskMode.DRAFT,
        server_default=TaskMode.DRAFT.value,
        comment="全局默认运行模式：draft / publish",
    )
    aigc_model: Mapped[AigcModel] = mapped_column(
        SAEnum(
            AigcModel,
            name="aigc_model_enum",
            create_type=True,
            values_callable=enum_values,
        ),
        nullable=False,
        default=DEFAULT_AIGC_MODEL,
        server_default=DEFAULT_AIGC_MODEL.value,
        comment="AIGC 模型：ds_v3（DeepSeek）/ ernie（文心一言）",
    )
    account_delay: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_ACCOUNT_DELAY,
        server_default=str(DEFAULT_ACCOUNT_DELAY),
        comment="账号间延迟（秒），有效范围 1-300",
    )
    max_concurrent_accounts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_MAX_CONCURRENT_ACCOUNTS,
        server_default=str(DEFAULT_MAX_CONCURRENT_ACCOUNTS),
        comment="跨账号最大并发数，有效范围 1-3",
    )
    daily_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_DAILY_LIMIT,
        server_default=str(DEFAULT_DAILY_LIMIT),
        comment="单账号每日最大执行次数（含 draft + publish）",
    )

    # ── 超时配置 ─────────────────────────────────────────────────────────────

    task_timeout_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_TASK_TIMEOUT_MINUTES,
        server_default=str(DEFAULT_TASK_TIMEOUT_MINUTES),
        comment="单任务总超时（分钟），兜底保障",
    )
    generate_timeout: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_GENERATE_TIMEOUT,
        server_default=str(DEFAULT_GENERATE_TIMEOUT),
        comment="AI 生成步骤超时（秒）",
    )
    polish_timeout: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_POLISH_TIMEOUT,
        server_default=str(DEFAULT_POLISH_TIMEOUT),
        comment="AI 润色步骤超时（秒）",
    )
    cover_timeout: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_COVER_TIMEOUT,
        server_default=str(DEFAULT_COVER_TIMEOUT),
        comment="封面搜索步骤超时（秒）",
    )
    publish_timeout: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_PUBLISH_TIMEOUT,
        server_default=str(DEFAULT_PUBLISH_TIMEOUT),
        comment="正式发布步骤超时（秒）",
    )
    draft_timeout: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_DRAFT_TIMEOUT,
        server_default=str(DEFAULT_DRAFT_TIMEOUT),
        comment="草稿保存步骤超时（秒）",
    )

    # ── 通知配置 ─────────────────────────────────────────────────────────────

    wecom_webhook: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="企业微信机器人 Webhook URL，为空则不发通知",
    )
    notify_level: Mapped[NotifyLevel] = mapped_column(
        SAEnum(
            NotifyLevel,
            name="notify_level_enum",
            create_type=True,
            values_callable=enum_values,
        ),
        nullable=False,
        default=NotifyLevel.FAILURE_ONLY,
        server_default=NotifyLevel.FAILURE_ONLY.value,
        comment="通知级别：all / failure_only / off",
    )

    # ── 认证配置 ─────────────────────────────────────────────────────────────

    admin_password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="管理员密码 bcrypt 哈希值，初始值由 ADMIN_PASSWORD 环境变量生成",
    )
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="JWT token 版本号，修改密码时 +1，使所有已签发 token 自动失效",
    )

    # ── 时间戳 ───────────────────────────────────────────────────────────────

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后更新时间（UTC）",
    )

    def __repr__(self) -> str:
        return f"<SystemSettings run_mode={self.run_mode} max_concurrent={self.max_concurrent_accounts}>"
