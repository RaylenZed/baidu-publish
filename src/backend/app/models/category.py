"""
categories 表：系统品类主数据。

设计目标：
  - 将原先硬编码在 constants.py 中的品类列表迁移为数据库真源
  - 为前端下拉、账号绑定、变量池配置提供统一品类来源
  - 支持后台新增、重命名、启停、排序
"""

from __future__ import annotations

from sqlalchemy import Boolean, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        comment="主键",
    )
    name: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        comment="品类名称，全局唯一，长度 1-20",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否启用；停用后不再出现在新建表单下拉中",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="排序值，越小越靠前",
    )

    __table_args__ = (
        Index("ix_categories_enabled_sort_order", "enabled", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} enabled={self.enabled}>"
