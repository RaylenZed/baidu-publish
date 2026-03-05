"""
variable_pools 表：6 维变量池配置。
combo_history 表：变量组合使用历史。

变量池分类（来源 PRD §6.5）:
  品类专属：angle（角度）、persona（人设）—— 每个品类各一套
  全品类通用：style（风格）、structure（结构）、title_style（标题风格）、time_hook（时间场景）

items 字段结构（JSONB 对象数组）:
  [{"value": "书单推荐", "weight": 1, "enabled": true}, ...]

combo_id 格式（PRD POOL-05）:
  A{角度序号}P{人设序号}S{风格序号}T{标题风格序号}
  示例：A3P2S1T4

注意：PRD 中 variable_pools 仅有 updated_at，此处补充 created_at 用于审计。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from app.core.constants import PoolType

if TYPE_CHECKING:
    from .account import Account
    from .task import Task


class VariablePool(Base):
    __tablename__ = "variable_pools"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    pool_type: Mapped[PoolType] = mapped_column(
        SAEnum(PoolType, name="pool_type_enum", create_type=True),
        nullable=False,
        comment="池类型：angle / persona / style / structure / title_style / time_hook",
    )
    category: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="品类名（品类专属池）；NULL 表示全品类通用池",
    )
    items: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        comment="池项目数组，结构：[{value: str, weight: int, enabled: bool}]；至少 1 项（POOL-03）",
    )
    # PRD 仅定义 updated_at，补充 created_at
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="首次创建时间（UTC）—— PRD 补充字段",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后更新时间（UTC）",
    )

    __table_args__ = (
        UniqueConstraint("pool_type", "category", name="uq_variable_pools_type_category"),
    )

    def __repr__(self) -> str:
        return f"<VariablePool id={self.id} type={self.pool_type} category={self.category!r}>"


class ComboHistory(Base):
    __tablename__ = "combo_history"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        comment="使用此组合的账号 ID",
    )
    category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="品类名",
    )
    combo_id: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="变量组合标识，格式 A{角度}P{人设}S{风格}T{标题风格}",
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联任务 ID（PRD 补充字段，补 P-5）：便于从组合历史反查具体任务，支持二期效果归因",
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="使用时间（UTC），即任务创建时间",
    )

    # ── Relationships ────────────────────────────────────────────────────────

    account: Mapped[Account] = relationship(
        "Account",
        back_populates="combo_histories",
    )
    task: Mapped[Task | None] = relationship(
        "Task",
        foreign_keys=[task_id],
    )

    # ── Indexes ──────────────────────────────────────────────────────────────

    __table_args__ = (
        Index("ix_combo_history_account_category_used_at", "account_id", "category", "used_at"),
    )

    def __repr__(self) -> str:
        return f"<ComboHistory id={self.id} account_id={self.account_id} combo_id={self.combo_id!r}>"
