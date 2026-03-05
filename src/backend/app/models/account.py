"""
accounts 表：百家号账号信息。

业务规则（来源 PRD §8.1）:
  ACC-01  每个账号绑定 1-2 个品类，不可超过 2 个（DTO 层校验）
  ACC-02  账号名称全局唯一（UNIQUE 约束）
  ACC-03  Cookie 必须包含 BDUSS=（DTO 层校验）
  ACC-04  Cookie 状态：active / expired / unchecked
  ACC-05  删除前检查未完成任务（Service 层）
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from app.core.constants import CookieStatus

if TYPE_CHECKING:
    from .task import Task
    from .schedule import ScheduleAccount
    from .pool import ComboHistory
    from .audit import ContentEvent


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        comment="账号名称，全局唯一，长度 1-50",
    )
    cookie_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="AES-256-CBC 加密后的 Cookie 字符串，明文必须包含 BDUSS=",
    )
    categories: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        comment="绑定品类列表（1-2 个），如 [\"图书教育\"]",
    )
    cookie_status: Mapped[CookieStatus] = mapped_column(
        SAEnum(CookieStatus, name="cookie_status_enum", create_type=True),
        nullable=False,
        default=CookieStatus.UNCHECKED,
        server_default=CookieStatus.UNCHECKED.value,
        comment="Cookie 状态：active / expired / unchecked",
    )
    cookie_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="上次 Cookie 检测时间（UTC）",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    tasks: Mapped[list[Task]] = relationship(
        "Task",
        back_populates="account",
        foreign_keys="Task.account_id",
    )
    schedule_accounts: Mapped[list[ScheduleAccount]] = relationship(
        "ScheduleAccount",
        back_populates="account",
        cascade="all, delete-orphan",
    )
    combo_histories: Mapped[list[ComboHistory]] = relationship(
        "ComboHistory",
        back_populates="account",
        cascade="all, delete-orphan",
    )
    content_events: Mapped[list[ContentEvent]] = relationship(
        "ContentEvent",
        back_populates="account",
    )

    # ── Indexes ──────────────────────────────────────────────────────────────

    __table_args__ = (
        # P-6 补充：JSONB 字段 categories 上的 GIN 索引，支持高效查询 "绑定了品类 X 的所有账号"
        # 用法示例：WHERE categories @> '["图书教育"]'
        Index(
            "ix_accounts_categories_gin",
            "categories",
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        return f"<Account id={self.id} name={self.name!r} status={self.cookie_status}>"
