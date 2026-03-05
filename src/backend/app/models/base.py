"""
SQLAlchemy 2.0 声明式基类与公共 Mixin。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有模型的基类。"""
    pass


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
