"""
schedules 表：定时任务配置。
schedule_accounts 表：定时任务与账号的 M:N 关联。

Misfire 策略（来源 PRD TASK-11）:
  系统重启后，若 next_fire_at < NOW() 且距 last_fired_at 不超过 24 小时，补执行一次。
  超过 24 小时的错过不补执行，仅记录 WARN 日志。

schedule_accounts:
  - 联合主键 (schedule_id, account_id)
  - 删除账号时 ON DELETE CASCADE 自动清理关联（CLAUDE.md 架构决策 #8）
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from app.core.constants import TaskMode

if TYPE_CHECKING:
    from .account import Account
    from .task import Task


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="定时任务名称，如「每日9点发布」",
    )
    cron_expr: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Cron 表达式，如 0 9 * * *",
    )
    mode: Mapped[TaskMode] = mapped_column(
        SAEnum(TaskMode, name="task_mode_enum", create_type=False),  # 复用已建的 enum type
        nullable=False,
        comment="运行模式：draft / publish",
    )
    timezone: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
        comment="调度时区，默认 Asia/Shanghai",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否启用，False 时 Celery Beat 不触发",
    )
    last_fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="上次触发时间（UTC），用于 Misfire 判断",
    )
    next_fire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="下次触发时间（UTC），由 schedule_service 计算写入",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    schedule_accounts: Mapped[list[ScheduleAccount]] = relationship(
        "ScheduleAccount",
        back_populates="schedule",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list[Task]] = relationship(
        "Task",
        back_populates="schedule",
    )

    def __repr__(self) -> str:
        return f"<Schedule id={self.id} name={self.name!r} enabled={self.enabled}>"


class ScheduleAccount(Base):
    """schedules ↔ accounts 的 M:N 关联表。"""

    __tablename__ = "schedule_accounts"

    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedules.id", ondelete="CASCADE"),
        primary_key=True,
        comment="定时任务 ID",
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        primary_key=True,
        comment="账号 ID",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    schedule: Mapped[Schedule] = relationship(
        "Schedule",
        back_populates="schedule_accounts",
    )
    account: Mapped[Account] = relationship(
        "Account",
        back_populates="schedule_accounts",
    )

    __table_args__ = (
        UniqueConstraint("schedule_id", "account_id", name="uq_schedule_accounts"),
    )

    def __repr__(self) -> str:
        return f"<ScheduleAccount schedule_id={self.schedule_id} account_id={self.account_id}>"
