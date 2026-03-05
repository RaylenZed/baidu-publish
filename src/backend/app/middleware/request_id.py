"""
RequestIdMiddleware：为每个请求注入唯一 request_id。

- 优先读取客户端传入的 X-Request-ID 请求头
- 否则自动生成 UUID4
- 写入 request.state.request_id，供日志和错误响应使用
- 响应头中回传 X-Request-ID
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
