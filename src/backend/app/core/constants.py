"""
业务常量与枚举定义。

所有枚举值为后端单一枚举源，前端通过 API 拉取，不允许本地硬编码。
"""

from __future__ import annotations

import enum
from typing import Final


# ── Cookie 状态 ──────────────────────────────────────────────────────────────

class CookieStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    UNCHECKED = "unchecked"


# ── 任务相关 ─────────────────────────────────────────────────────────────────

class TaskMode(str, enum.Enum):
    DRAFT = "draft"
    PUBLISH = "publish"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    TIMEOUT = "timeout"


class TaskErrorType(str, enum.Enum):
    # AIGC 类
    AIGC_TIMEOUT = "aigc_timeout"
    CONNECTION_ERROR = "connection_error"
    PARSE_ERROR = "parse_error"
    EMPTY_RESPONSE = "empty_response"
    # 发布类
    PUBLISH_FAILED_DRAFT_SAVED = "publish_failed_draft_saved"
    TOKEN_REFRESH_FAILED = "token_refresh_failed"
    # 系统类
    TIMEOUT = "timeout"
    WORKER_CRASH = "worker_crash"


class TaskWarning(str, enum.Enum):
    PARTIAL_CONTENT = "partial_content"


class TaskStep(str, enum.Enum):
    PROMPT = "prompt"
    GENERATE = "generate"
    POLISH = "polish"
    DRAFT = "draft"
    COVER = "cover"
    PUBLISH = "publish"


# ── 文章相关 ─────────────────────────────────────────────────────────────────

class PublishStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PUBLISH_FAILED = "publish_failed"


class ContentWarning(str, enum.Enum):
    PARTIAL_CONTENT = "partial_content"


# ── 日志相关 ─────────────────────────────────────────────────────────────────

class LogLevel(str, enum.Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


# ── 变量池相关 ───────────────────────────────────────────────────────────────

class PoolType(str, enum.Enum):
    ANGLE = "angle"              # 角度池（品类专属）
    PERSONA = "persona"          # 人设池（品类专属）
    STYLE = "style"              # 风格池（通用）
    STRUCTURE = "structure"      # 结构池（通用）
    TITLE_STYLE = "title_style"  # 标题风格池（通用）
    TIME_HOOK = "time_hook"      # 时间场景池（通用）


# ── 事件相关 ─────────────────────────────────────────────────────────────────

class ContentEventType(str, enum.Enum):
    TASK_CREATED = "task_created"
    TASK_SUCCEEDED = "task_succeeded"
    TASK_FAILED = "task_failed"
    ARTICLE_PUBLISHED = "article_published"


# ── 系统设置相关 ─────────────────────────────────────────────────────────────

class AigcModel(str, enum.Enum):
    DS_V3 = "ds_v3"    # DeepSeek V3
    ERNIE = "ernie"    # 文心一言


class NotifyLevel(str, enum.Enum):
    ALL = "all"
    FAILURE_ONLY = "failure_only"
    OFF = "off"


# ── 品类常量 ─────────────────────────────────────────────────────────────────

CATEGORIES: Final[list[str]] = [
    "图书教育", "家用日常", "精品服饰", "食品生鲜",
    "数码家电", "美妆个护", "母婴用品", "运动户外",
    "鞋靴箱包", "汽车用品", "珠宝配饰", "宠物用品",
    "鲜花园艺", "零食干货", "粮油调料", "医疗保健",
    "家用器械", "中医养生",
]

# PRD PUB-05: 品类 → 百家号文章分类精确映射；失败兜底见 BJH_CATEGORY_FALLBACK
CATEGORY_TO_BJH: Final[dict[str, tuple[str, str]]] = {
    "图书教育": ("教育", "读书"),
    "家用日常": ("生活", "家居"),
    "精品服饰": ("时尚", "穿搭"),
    "食品生鲜": ("美食", "食材"),
    "数码家电": ("科技", "数码"),
    "美妆个护": ("时尚", "美妆"),
    "母婴用品": ("亲子", "母婴"),
    "运动户外": ("体育", "户外"),
    "鞋靴箱包": ("时尚", "箱包"),
    "汽车用品": ("汽车", "配件"),
    "珠宝配饰": ("时尚", "珠宝"),
    "宠物用品": ("宠物", "用品"),
    "鲜花园艺": ("生活", "园艺"),
    "零食干货": ("美食", "零食"),
    "粮油调料": ("美食", "厨房"),
    "医疗保健": ("健康", "保健"),
    "家用器械": ("健康", "器械"),
    "中医养生": ("健康", "中医"),
}

BJH_CATEGORY_FALLBACK: Final[tuple[str, str]] = ("生活", "生活技巧")


# ── 系统默认值 ───────────────────────────────────────────────────────────────

DEFAULT_AIGC_MODEL: Final[AigcModel] = AigcModel.DS_V3  # AI 生成模型默认值
DEFAULT_ACCOUNT_DELAY: Final[int] = 10           # 账号间延迟（秒）
DEFAULT_MAX_CONCURRENT_ACCOUNTS: Final[int] = 1  # 跨账号并发数
DEFAULT_DAILY_LIMIT: Final[int] = 3              # 单账号每日上限
DEFAULT_TASK_TIMEOUT_MINUTES: Final[int] = 15    # 总超时（分钟）
DEFAULT_GENERATE_TIMEOUT: Final[int] = 240       # AI 生成超时（秒）
DEFAULT_POLISH_TIMEOUT: Final[int] = 240         # AI 润色超时（秒）
DEFAULT_COVER_TIMEOUT: Final[int] = 60           # 封面搜索超时（秒）
DEFAULT_PUBLISH_TIMEOUT: Final[int] = 60         # 发布超时（秒）
DEFAULT_DRAFT_TIMEOUT: Final[int] = 60           # 草稿保存超时（秒）
