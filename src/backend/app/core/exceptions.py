"""
统一异常体系（CLAUDE.md §4.3 异常处理规范）。

分层约定：
  - Service 层抛 AppException 子类
  - Route 层不做 try/except（由全局处理器兜底）
  - 全局处理器在 main.py 注册，统一转换为标准错误结构：
    { "success": false, "errorCode": "MODULE_REASON", "message": "...",
      "requestId": "...", "details": {} }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    """所有业务异常的基类。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


# ── 认证类 ───────────────────────────────────────────────────────────────────

class UnauthorizedException(AppException):
    def __init__(self, message: str = "未登录或 Token 已失效") -> None:
        super().__init__("AUTH_UNAUTHORIZED", message, status.HTTP_401_UNAUTHORIZED)


class ForbiddenException(AppException):
    def __init__(self, message: str = "权限不足") -> None:
        super().__init__("AUTH_FORBIDDEN", message, status.HTTP_403_FORBIDDEN)


class LoginRateLimitException(AppException):
    def __init__(self) -> None:
        super().__init__(
            "AUTH_RATE_LIMIT",
            "登录尝试过于频繁，请 15 分钟后再试",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )


# ── 账号类 ───────────────────────────────────────────────────────────────────

class AccountNotFoundException(AppException):
    def __init__(self, account_id: int) -> None:
        super().__init__(
            "ACCOUNT_NOT_FOUND",
            f"账号 {account_id} 不存在",
            status.HTTP_404_NOT_FOUND,
        )


class AccountNameDuplicateException(AppException):
    def __init__(self, name: str) -> None:
        super().__init__("ACCOUNT_NAME_DUPLICATE", f"账号名称「{name}」已存在")


class AccountCookieExpiredException(AppException):
    def __init__(self, account_id: int) -> None:
        super().__init__(
            "ACCOUNT_COOKIE_EXPIRED",
            f"账号 {account_id} 的 Cookie 已过期，请更新后重试",
        )


class AccountHasPendingTasksException(AppException):
    def __init__(self, account_id: int) -> None:
        super().__init__(
            "ACCOUNT_HAS_PENDING_TASKS",
            f"账号 {account_id} 存在未完成任务，请先取消或等待任务结束",
        )


# ── 任务类 ───────────────────────────────────────────────────────────────────

class TaskNotFoundException(AppException):
    def __init__(self, task_id: int) -> None:
        super().__init__(
            "TASK_NOT_FOUND", f"任务 {task_id} 不存在", status.HTTP_404_NOT_FOUND
        )


class TaskDailyLimitExceededException(AppException):
    def __init__(self, account_id: int, limit: int) -> None:
        super().__init__(
            "TASK_DAILY_LIMIT_EXCEEDED",
            f"账号 {account_id} 今日已达执行上限 {limit} 次",
        )


class TaskDuplicateException(AppException):
    def __init__(self) -> None:
        super().__init__(
            "TASK_DUPLICATE", "60 秒内已存在相同账号+品类+模式的任务，请稍后再试"
        )


class TaskIdempotencyConflictException(AppException):
    def __init__(self) -> None:
        super().__init__(
            "TASK_IDEMPOTENCY_CONFLICT", "相同 idempotency_key 的任务已创建"
        )


class TaskCoolingDownException(AppException):
    def __init__(self, account_id: int) -> None:
        super().__init__(
            "TASK_COOLING_DOWN",
            f"账号 {account_id} 连续失败 3 次，冷却中，请 30 分钟后重试",
        )


class TaskInvalidStatusException(AppException):
    def __init__(self, task_id: int, current: str, required: str) -> None:
        super().__init__(
            "TASK_INVALID_STATUS",
            f"任务 {task_id} 当前状态为 {current}，该操作需要 {required} 状态",
        )


# ── 文章类 ───────────────────────────────────────────────────────────────────

class ArticleNotFoundException(AppException):
    def __init__(self, article_id: int) -> None:
        super().__init__(
            "ARTICLE_NOT_FOUND",
            f"文章 {article_id} 不存在",
            status.HTTP_404_NOT_FOUND,
        )


class ArticlePublishBlockedByWarningException(AppException):
    def __init__(self) -> None:
        super().__init__(
            "ARTICLE_PUBLISH_BLOCKED",
            "文章内容不完整（partial_content），需人工确认后才可发布",
        )


# ── 通用类 ───────────────────────────────────────────────────────────────────

class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__("NOT_FOUND", message, status.HTTP_404_NOT_FOUND)


class ValidationException(AppException):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("VALIDATION_ERROR", message, status.HTTP_422_UNPROCESSABLE_CONTENT, details)


# ── 全局处理器注册 ────────────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """在 main.py 的 lifespan 之后调用，注册统一异常处理器。"""

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "errorCode": exc.code,
                "message": exc.message,
                "requestId": request_id,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "success": False,
                "errorCode": "VALIDATION_ERROR",
                "message": "请求参数校验失败",
                "requestId": request_id,
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "errorCode": "NOT_FOUND",
                "message": f"路径 {request.url.path} 不存在",
                "requestId": request_id,
                "details": {},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "errorCode": "INTERNAL_ERROR",
                "message": "服务器内部错误，请联系管理员",
                "requestId": request_id,
                "details": {},
            },
        )
