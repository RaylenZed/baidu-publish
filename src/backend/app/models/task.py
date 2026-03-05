"""
tasks 表：任务执行记录。

状态机（来源 PRD §10.1）:
  pending → running → success / failed / timeout
  pending → canceled

业务规则（来源 PRD §8.2）:
  TASK-01  同账号串行（Redis 账号锁，见 workers/tasks.py）
  TASK-03  单账号每日执行上限 3 次（task_service 创建前校验）
  TASK-04  状态流转见上方状态机
  TASK-05  重试创建新 task，原 task 保持 failed，通过 retry_of_task_id 追踪
  TASK-07  idempotency_key 去重（Redis TTL 5min 为主；tasks.idempotency_key 存库作 DB 兜底）
  TASK-08  连续失败 3 次冷却 30 分钟

注意：tasks.warning 为任务执行级警告，articles.content_warning 为内容级警告，
      partial_content 场景双写。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from app.core.constants import (
    TaskMode,
    TaskStatus,
    TaskErrorType,
    TaskWarning,
)

if TYPE_CHECKING:
    from .account import Account
    from .schedule import Schedule
    from .article import Article
    from .task_log import TaskLog
    from .audit import ContentEvent


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        comment="所属账号 ID",
    )
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"),
        nullable=True,
        comment="来源定时任务 ID，手动触发为 NULL",
    )
    retry_of_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="重试来源任务 ID，追踪重试链路；首次执行为 NULL",
    )
    category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="本次执行品类，取值范围见 CATEGORIES 常量",
    )
    mode: Mapped[TaskMode] = mapped_column(
        SAEnum(TaskMode, name="task_mode_enum", create_type=True),
        nullable=False,
        comment="运行模式：draft（仅草稿）/ publish（正式发布）",
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status_enum", create_type=True),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=TaskStatus.PENDING.value,
        comment="任务状态：pending / running / success / failed / canceled / timeout",
    )
    error_type: Mapped[TaskErrorType | None] = mapped_column(
        SAEnum(TaskErrorType, name="task_error_type_enum", create_type=True),
        nullable=True,
        comment="失败细分类型，仅 failed/timeout 状态有值",
    )
    warning: Mapped[TaskWarning | None] = mapped_column(
        SAEnum(TaskWarning, name="task_warning_enum", create_type=True),
        nullable=True,
        comment="任务执行级警告，如 partial_content（SSE 截断降级）",
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment=(
            "幂等 key（UUID，PRD 补充字段，补 P-7）：手动创建时由调用方传入；"
            "定时触发为 NULL。写入 tasks 提供 DB 级兜底去重（Redis 重启场景）。"
            "去重逻辑：查询 created_at > NOW()-5min 且 key 相同的记录。"
        ),
    )
    combo_id: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="变量组合标识，格式 A{角度}P{人设}S{风格}T{标题风格}",
    )
    topic_keyword: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="用户指定的主题关键词（可选）",
    )
    product_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="用户指定的产品/品牌名（可选）",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="失败原因详情",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Worker 拾取任务时间（UTC）",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="任务完成时间（UTC），含成功/失败/超时",
    )
    timeout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="超时截止时间（UTC），Worker 拾取时设置 = started_at + task_timeout_minutes",
    )
    last_step_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近步骤完成时间（UTC），用于步骤级超时判定",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="任务创建时间（UTC）",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    account: Mapped[Account] = relationship(
        "Account",
        back_populates="tasks",
        foreign_keys=[account_id],
    )
    schedule: Mapped[Schedule | None] = relationship(
        "Schedule",
        back_populates="tasks",
    )
    retry_origin: Mapped[Task | None] = relationship(
        "Task",
        remote_side="Task.id",
        foreign_keys=[retry_of_task_id],
    )
    article: Mapped[Article | None] = relationship(
        "Article",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
    )
    logs: Mapped[list[TaskLog]] = relationship(
        "TaskLog",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskLog.created_at",
    )
    content_events: Mapped[list[ContentEvent]] = relationship(
        "ContentEvent",
        back_populates="task",
    )

    # ── Indexes ──────────────────────────────────────────────────────────────

    __table_args__ = (
        Index("ix_tasks_status_created_at", "status", "created_at"),
        Index("ix_tasks_account_id_created_at", "account_id", "created_at"),
        Index("ix_tasks_category_created_at", "category", "created_at"),
        # P-7 补充：幂等 key 索引，查询 created_at > NOW()-5min AND idempotency_key = ? 时走此索引
        Index("ix_tasks_idempotency_key", "idempotency_key"),
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} account_id={self.account_id} status={self.status}>"
