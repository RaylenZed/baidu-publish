"""
统一导出所有 SQLAlchemy 模型，确保 Alembic autogenerate 能扫描到全部表。

导入顺序遵循依赖关系：被依赖的表先导入，避免循环导入问题。
"""

from .base import Base, TimestampMixin  # noqa: F401

# 无外键依赖的表
from .system_settings import SystemSettings  # noqa: F401
from .schedule import Schedule, ScheduleAccount  # noqa: F401
from .pool import VariablePool, ComboHistory  # noqa: F401

# 依赖 accounts
from .account import Account  # noqa: F401

# 依赖 accounts + schedules
from .task import Task  # noqa: F401

# 依赖 tasks
from .article import Article  # noqa: F401
from .task_log import TaskLog  # noqa: F401

# 依赖 articles / tasks / accounts
from .audit import PublishAttempt, ContentEvent  # noqa: F401

__all__ = [
    "Base",
    "TimestampMixin",
    "Account",
    "Task",
    "Article",
    "TaskLog",
    "Schedule",
    "ScheduleAccount",
    "VariablePool",
    "ComboHistory",
    "PublishAttempt",
    "ContentEvent",
    "SystemSettings",
]
