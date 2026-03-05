"""
审计服务（PRD §CLAUDE.md §3 #11 审计可追踪）

职责：
  - publish_attempts 记录每次发布调用结果
  - content_events 记录关键生命周期事件

事件类型（ContentEventType）：
  - task_created: 任务创建时
  - task_succeeded: 任务成功完成时
  - task_failed: 任务失败时
  - article_published: 文章发布成功时
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ContentEvent, PublishAttempt


class AuditService:
    """审计日志写入。"""

    async def record_publish_attempt(
        self,
        db: AsyncSession,
        article_id: int,
        request_summary: dict | None = None,
        response_code: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        记录一次发布调用（PRD publish_attempts 表）。
        调用方负责 commit。
        """
        attempt = PublishAttempt(
            article_id=article_id,
            request_summary=request_summary,
            response_code=response_code,
            error_type=error_type,
            error_message=error_message,
        )
        db.add(attempt)

    async def record_content_event(
        self,
        db: AsyncSession,
        event_type: str,
        account_id: int,
        category: str,
        task_id: int | None = None,
        payload: dict | None = None,
    ) -> None:
        """
        记录内容生命周期事件（PRD content_events 表）。
        调用方负责 commit。
        """
        from app.core.constants import ContentEventType

        # 验证 event_type 有效
        try:
            ContentEventType(event_type)
        except ValueError:
            event_type = ContentEventType.TASK_CREATED.value

        event = ContentEvent(
            event_type=event_type,
            task_id=task_id,
            account_id=account_id,
            category=category,
            payload=payload,
        )
        db.add(event)