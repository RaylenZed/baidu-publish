"""
FastAPI 应用入口（PRD §11 / CLAUDE.md §5 目录结构）

路由挂载：
  /api/v1/auth          认证（登录、刷新 token、签发 ws_ticket）
  /api/v1/dashboard     仪表盘聚合接口
  /api/v1/accounts      账号管理
  /api/v1/tasks         任务管理
  /api/v1/articles      文章管理
  /api/v1/schedules     定时任务管理
  /api/v1/pools         变量池管理
  /api/v1/settings      系统配置
  /api/v1/settings/logs 系统日志
  /ws/tasks/{task_id}/logs  实时日志 WebSocket

中间件栈（按挂载顺序）：
  RequestIdMiddleware → CORSMiddleware
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.routes import (
    accounts,
    articles,
    auth,
    dashboard,
    pools,
    schedules,
    settings,
    system_logs,
    tasks,
)
from app.core.config import settings as app_settings
from app.core.database import close_db, init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.middleware.request_id import RequestIdMiddleware
from app.ws.task_log_stream import handle_task_log_stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化 DB，关闭时清理连接。"""
    setup_logging()
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="百家号自动化发布管理系统",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── 中间件 ──────────────────────────────────────────────────────────────────
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局异常处理 ─────────────────────────────────────────────────────────────
register_exception_handlers(app)

# ── REST 路由 ────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"

app.include_router(auth.router,        prefix=f"{API_PREFIX}/auth",          tags=["认证"])
app.include_router(dashboard.router,   prefix=f"{API_PREFIX}/dashboard",     tags=["仪表盘"])
app.include_router(accounts.router,    prefix=f"{API_PREFIX}/accounts",      tags=["账号管理"])
app.include_router(tasks.router,       prefix=f"{API_PREFIX}/tasks",         tags=["任务管理"])
app.include_router(articles.router,    prefix=f"{API_PREFIX}/articles",      tags=["文章管理"])
app.include_router(schedules.router,   prefix=f"{API_PREFIX}/schedules",     tags=["定时任务"])
app.include_router(pools.router,       prefix=f"{API_PREFIX}/pools",         tags=["变量池"])
app.include_router(settings.router,    prefix=f"{API_PREFIX}/settings",      tags=["系统设置"])
app.include_router(system_logs.router, prefix=f"{API_PREFIX}/settings",      tags=["系统日志"])


# ── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws/tasks/{task_id}/logs")
async def ws_task_logs(
    websocket: WebSocket,
    task_id: int,
    ticket: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """实时任务日志推送（PRD §11.4 / CLAUDE.md §3 #9-10）。"""
    await handle_task_log_stream(websocket, task_id, ticket, db)


# ── 健康检查 ─────────────────────────────────────────────────────────────────
@app.get("/health", tags=["运维"])
async def health_check() -> dict:
    return {"status": "ok"}
