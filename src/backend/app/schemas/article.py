"""
文章管理 Pydantic DTO（PRD §6.4 / §11.5）
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import ContentWarning, PublishStatus


class ArticleResponse(BaseModel):
    """文章列表 / 详情响应。"""
    id: int
    task_id: int
    title: str
    body_md: str
    body_html: str
    raw_draft: str | None
    bjh_article_id: str | None
    cover_url: str | None
    publish_status: PublishStatus
    content_warning: ContentWarning | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArticleUpdateRequest(BaseModel):
    """在线编辑文章（仅允许编辑 draft 状态文章）。"""
    title: str = Field(..., min_length=1, max_length=100)
    body_md: str = Field(..., min_length=1)
