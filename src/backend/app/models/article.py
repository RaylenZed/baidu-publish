"""
articles 表：AI 生成的文章内容与发布状态。

发布状态机（来源 PRD §10.2）:
  draft → publishing → published
  publishing → publish_failed → publishing（重试）
  publish_failed → draft（编辑后重新保存）

注意：
  - body_md 为润色后正文，raw_draft 为 AI 初稿（对比用）
  - content_warning 为内容级警告（展示给用户），与 tasks.warning 语义不同
  - partial_content 场景：tasks.warning 和 articles.content_warning 均写入
  - PRD 未定义 created_at/updated_at，此处补充（文章可被编辑，需追踪更新时间）
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, enum_values
from app.core.constants import PublishStatus, ContentWarning

if TYPE_CHECKING:
    from .task import Task
    from .audit import PublishAttempt


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="关联任务 ID（1:1 唯一）",
    )
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="文章标题",
    )
    body_md: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="润色后 Markdown 正文",
    )
    body_html: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="转换后的百家号 HTML 正文",
    )
    raw_draft: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI 初稿原文（用于初稿/润色对比展示）",
    )
    bjh_article_id: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="百家号平台侧 article_id，草稿保存成功后写入",
    )
    cover_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="封面图 URL，搜索失败允许为空（PUB-04）",
    )
    publish_status: Mapped[PublishStatus] = mapped_column(
        SAEnum(
            PublishStatus,
            name="publish_status_enum",
            create_type=True,
            values_callable=enum_values,
        ),
        nullable=False,
        default=PublishStatus.DRAFT,
        server_default=PublishStatus.DRAFT.value,
        comment="发布状态：draft / publishing / published / publish_failed",
    )
    content_warning: Mapped[ContentWarning | None] = mapped_column(
        SAEnum(
            ContentWarning,
            name="content_warning_enum",
            create_type=True,
            values_callable=enum_values,
        ),
        nullable=True,
        comment="内容级警告（文章列表展示橙色 Tag），如 partial_content（SSE 截断）",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="发布成功时间（UTC）",
    )
    # PRD 未列出，补充：文章可被编辑，需要时间追踪
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="文章创建时间（UTC）—— PRD 补充字段",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后编辑时间（UTC）—— PRD 补充字段",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    task: Mapped[Task] = relationship(
        "Task",
        back_populates="article",
    )
    publish_attempts: Mapped[list[PublishAttempt]] = relationship(
        "PublishAttempt",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="PublishAttempt.attempted_at",
    )

    # ── Indexes ──────────────────────────────────────────────────────────────

    __table_args__ = (
        Index("ix_articles_publish_status_created_at", "publish_status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Article id={self.id} task_id={self.task_id} publish_status={self.publish_status}>"
