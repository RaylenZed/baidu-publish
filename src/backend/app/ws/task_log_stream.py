"""
WebSocket 实时日志流（PRD §11.4 / PRD §6.3.3）
路径：WS /ws/tasks/{task_id}/logs?ticket=xxx

数据通路（CLAUDE.md 架构决策 #10）：
  1. 连接时先从 DB 回放 task_logs 表的历史日志
  2. 再订阅 Redis Pub/Sub 频道 task:{task_id}:logs 推送增量
  3. 任务终态（success/failed/timeout/canceled）时发送 done 事件并关闭
  4. ws_ticket 用于连接鉴权（60 秒有效、单次消费）

消息格式（JSON）：
  历史 : {"type": "log",  "id": 1, "step": "generate", "level": "INFO",
           "message": "...", "ts": "2026-03-04T10:00:00Z"}
  增量 : {"type": "log",  "id": 2, ...}
  分界 : {"type": "history_end"}
  完成 : {"type": "done",  "status": "success"}
  错误 : {"type": "error", "message": "..."}

Worker 推送格式（同上 log 消息，通过 publish_log() 辅助函数）：
  redis.publish("task:{task_id}:logs", json.dumps({...}))
"""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_ws_ticket
from app.core.config import settings
from app.core.constants import TaskStatus
from app.core.logging import get_logger
from app.models.task import Task
from app.models.task_log import TaskLog

logger = get_logger(__name__)

REDIS_LOG_CHANNEL_TPL = "task:{task_id}:logs"

# 任务终态集合，收到这些状态后关闭 WS
_TERMINAL_STATUSES = {
    TaskStatus.SUCCESS,
    TaskStatus.FAILED,
    TaskStatus.TIMEOUT,
    TaskStatus.CANCELED,
}


async def handle_task_log_stream(
    websocket: WebSocket,
    task_id: int,
    ticket: str,
    db: AsyncSession,
) -> None:
    """
    WebSocket handler：
      1. 校验 ws_ticket（失败则直接关闭，不 accept）
      2. 发送历史日志
      3. 订阅 Redis Pub/Sub 实时推送，直到任务终态或客户端断开
    """
    # 1. 票据鉴权（失败时发 4403 关闭，不 accept）
    try:
        await verify_ws_ticket(ticket)
    except HTTPException as exc:
        await websocket.close(code=4403, reason=exc.detail)
        return

    await websocket.accept()

    try:
        # 2. 回放历史日志
        stmt = (
            select(TaskLog)
            .where(TaskLog.task_id == task_id)
            .order_by(TaskLog.id)
        )
        result = await db.execute(stmt)
        logs = result.scalars().all()
        for log in logs:
            await websocket.send_text(
                json.dumps({
                    "type": "log",
                    "id": log.id,
                    "step": log.step,
                    "level": log.level,
                    "message": log.message,
                    "ts": log.created_at.isoformat(),
                })
            )
        await websocket.send_text(json.dumps({"type": "history_end"}))

        # 若任务已处于终态，直接发 done 并关闭
        task = await db.get(Task, task_id)
        if task and task.status in _TERMINAL_STATUSES:
            await websocket.send_text(
                json.dumps({"type": "done", "status": task.status})
            )
            return

        # 3. 订阅 Redis Pub/Sub 实时推送
        channel = REDIS_LOG_CHANNEL_TPL.format(task_id=task_id)
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            async with client.pubsub() as pubsub:
                await pubsub.subscribe(channel)
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    data_str = message["data"]
                    # 转发给客户端
                    await websocket.send_text(data_str)
                    # 检测 done 事件 → 关闭
                    try:
                        parsed = json.loads(data_str)
                        if parsed.get("type") == "done":
                            break
                    except (json.JSONDecodeError, TypeError):
                        pass
        finally:
            await client.aclose()

    except WebSocketDisconnect:
        logger.info("WS 客户端断开", extra={"task_id": task_id})
    except Exception as exc:
        logger.error("WS 异常: %s", exc, extra={"task_id": task_id})
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
            await websocket.close(code=1011)
        except Exception:
            pass


# ── Worker 辅助：发布日志到 Redis Pub/Sub ─────────────────────────────────────

async def publish_log(
    redis_client: aioredis.Redis,
    task_id: int,
    step: str,
    level: str,
    message: str,
    ts: str,
    log_id: int = 0,
) -> None:
    """
    Worker 调用此函数将新日志推送到 Redis Pub/Sub。
    ts 为 ISO-8601 字符串（UTC）。log_id=0 表示 DB ID 未知（不影响客户端显示）。
    """
    channel = REDIS_LOG_CHANNEL_TPL.format(task_id=task_id)
    payload = json.dumps({
        "type": "log",
        "id": log_id,
        "step": step,
        "level": level,
        "message": message,
        "ts": ts,
    })
    await redis_client.publish(channel, payload)


async def publish_done(
    redis_client: aioredis.Redis,
    task_id: int,
    status: str,
) -> None:
    """
    任务结束时 Worker 调用，通知所有订阅者关闭连接。
    """
    channel = REDIS_LOG_CHANNEL_TPL.format(task_id=task_id)
    await redis_client.publish(channel, json.dumps({"type": "done", "status": status}))
