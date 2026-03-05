"""
SQLAlchemy 2.0 声明式基类与公共 Mixin。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有模型的基类。"""
    pass


def enum_values(enum_cls: type[PyEnum]) -> list[str]:
    """
    返回枚举 value 列表，供 SQLAlchemy Enum(values_callable=...) 使用。

    目的：统一按枚举 value（如 "draft"）持久化，避免默认按 Enum.name
    （如 "DRAFT"）写库导致与 PostgreSQL enum 标签不一致。
    """
    return [str(item.value) for item in enum_cls]


class TimestampMixin:
    """
    为需要 created_at / updated_at 的表提供公共时间戳字段。

    - 时间均存储为 TIMESTAMPTZ（带时区），实际值为 UTC。
    - created_at / updated_at 由后端（数据库）生成，禁止前端直传。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间（UTC）",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后更新时间（UTC）",
    )
