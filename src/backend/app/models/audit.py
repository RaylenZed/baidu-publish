"""
publish_attempts 表：发布 API 调用记录（轻量审计）。
content_events 表：关键生命周期事件（用于二期效果归因）。

publish_attempts 用途：
  - 记录每次调用百家号发布 API 的请求摘要、响应码、错误信息
  - 一期仅落盘，不做报表 UI

content_events 用途：
  - 结构化事件落盘（4 类事件）
  - 二期 A/B 分析和效果归因的前置数据基础
  - 一期不做报表 UI

注意：两张表均为 insert-only 审计表，无 updated_at。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, enum_values
from app.core.constants import ContentEventType

if TYPE_CHECKING:
    from .article import Article
    from .task import Task
    from .account import Account


class PublishAttempt(Base):
    __tablename__ = "publish_attempts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属文章 ID",
    )
    request_summary: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="发布请求参数摘要（脱敏），便于排查问题",
    )
    response_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="百家号 API 响应码（errno），0 表示成功",
    )
    error_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="错误分类，取值见 TaskErrorType 枚举",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误详情",
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="发布尝试时间（UTC）",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    article: Mapped[Article] = relationship(
        "Article",
        back_populates="publish_attempts",
    )

    # ── Indexes ──────────────────────────────────────────────────────────────

    __table_args__ = (
        Index("ix_publish_attempts_article_id_attempted_at", "article_id", "attempted_at"),
    )

    def __repr__(self) -> str:
        return f"<PublishAttempt id={self.id} article_id={self.article_id} response_code={self.response_code}>"


class ContentEvent(Base):
    __tablename__ = "content_events"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    event_type: Mapped[ContentEventType] = mapped_column(
        SAEnum(
            ContentEventType,
            name="content_event_type_enum",
            create_type=True,
            values_callable=enum_values,
        ),
        nullable=False,
        comment="事件类型：task_created / task_succeeded / task_failed / article_published",
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联任务 ID（可为 NULL）",
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        comment="关联账号 ID（冗余字段，便于直接按账号查询事件）",
    )
    category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="品类名",
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="事件上下文快照，如 {combo_id, mode, error_type}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="事件发生时间（UTC）",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    task: Mapped[Task | None] = relationship(
        "Task",
        back_populates="content_events",
    )
    account: Mapped[Account] = relationship(
        "Account",
        back_populates="content_events",
    )

    # ── Indexes ──────────────────────────────────────────────────────────────

    __table_args__ = (
        Index("ix_content_events_event_type_created_at", "event_type", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ContentEvent id={self.id} type={self.event_type} account_id={self.account_id}>"
