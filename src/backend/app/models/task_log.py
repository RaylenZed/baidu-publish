"""
task_logs 表：任务执行的逐步骤日志。

特性：
  - 日志不可变（insert-only），无 updated_at
  - Worker 写入后同步 publish 到 Redis Pub/Sub 频道 task:{task_id}:logs（实时推送）
  - task_logs 为业务日志事实来源，30 天后自动清理（Celery Beat 定期清理）
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from app.core.constants import TaskStep, LogLevel

if TYPE_CHECKING:
    from .task import Task


class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属任务 ID",
    )
    step: Mapped[TaskStep] = mapped_column(
        SAEnum(TaskStep, name="task_step_enum", create_type=True),
        nullable=False,
        comment="执行步骤：prompt / generate / polish / draft / cover / publish",
    )
    level: Mapped[LogLevel] = mapped_column(
        SAEnum(LogLevel, name="log_level_enum", create_type=True),
        nullable=False,
        comment="日志级别：INFO / WARN / ERROR",
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="日志内容",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="日志写入时间（UTC）",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    task: Mapped[Task] = relationship(
        "Task",
        back_populates="logs",
    )

    # ── Indexes ──────────────────────────────────────────────────────────────

    __table_args__ = (
        Index("ix_task_logs_task_id_created_at", "task_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TaskLog id={self.id} task_id={self.task_id} step={self.step} level={self.level}>"
