"""
日志初始化（结构化 JSON 日志，CLAUDE.md §4.7）。

字段约定：ts / level / request_id / task_id / account_id / module / message
生产环境输出 JSON，本地开发可通过 LOG_FORMAT=text 切换为可读格式。
"""

from __future__ import annotations

import logging
import sys
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _resolve_log_timezone() -> ZoneInfo:
    from app.core.config import settings

    try:
        return ZoneInfo(settings.APP_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai")


class _JsonFormatter(logging.Formatter):
    """将标准 LogRecord 序列化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime

        payload: dict[str, Any] = {
            "ts": datetime.now(_resolve_log_timezone()).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        # 注入上下文字段（由 structlog / middleware 写入 extra）
        for key in ("request_id", "task_id", "account_id"):
            if (val := getattr(record, key, None)) is not None:
                payload[key] = val

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    """本地开发用可读格式。"""

    FORMAT = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self.FORMAT, datefmt="%H:%M:%S")

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        from datetime import datetime

        dt = datetime.fromtimestamp(record.created, tz=_resolve_log_timezone())
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def setup_logging() -> None:
    """应用启动时调用一次，配置根日志处理器。"""
    from app.core.config import settings

    formatter: logging.Formatter = (
        _TextFormatter() if settings.LOG_FORMAT == "text" else _JsonFormatter()
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)
    root.handlers.clear()
    root.addHandler(handler)

    # 静默第三方噪音
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """模块内获取 logger 的统一入口。"""
    return logging.getLogger(name)
