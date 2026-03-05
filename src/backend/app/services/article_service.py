"""
文章服务（PRD §6.3 文章管理 / PRD §10 partial_content 风控）

职责：
  - 文章保存与状态流转（draft → publishing → published / publish_failed）
  - partial_content 风控：写入 content_warning，强制 draft_only 降级
  - 列表查询、详情、在线编辑
  - 手动发布（调用 BjhService + 状态流转）
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ContentWarning, PublishStatus
from app.core.exceptions import (
    ArticleNotFoundException,
    ArticlePublishBlockedByWarningException,
)
from app.models.article import Article


class ArticleService:
    """文章生命周期管理。"""

    # ── 公开方法 ──────────────────────────────────────────────────────────────

    async def save_article(
        self,
        db: AsyncSession,
        task_id: int,
        title: str,
        body_md: str,
        body_html: str,
        raw_draft: str | None = None,
    ) -> int:
        """
        保存文章草稿到 DB，返回 article_id（PRD §6.3.1）。
        调用方负责 commit 和 bjh_article_id 的写入（通过 update_publish_status）。
        """
        article = Article(
            task_id=task_id,
            title=title,
            body_md=body_md,
            body_html=body_html,
            raw_draft=raw_draft,
            publish_status=PublishStatus.DRAFT,
        )
        db.add(article)
        await db.flush()
        await db.refresh(article)
        return article.id

    async def mark_content_warning(
        self,
        db: AsyncSession,
        article_id: int,
        warning: ContentWarning,
    ) -> None:
        """
        标记内容风险（partial_content 触发，PRD §10）。
        调用方负责 commit。
        """
        article = await db.get(Article, article_id)
        if article is None:
            raise ArticleNotFoundException(article_id)
        article.content_warning = warning

    async def update_publish_status(
        self,
        db: AsyncSession,
        article_id: int,
        status: PublishStatus,
        bjh_article_id: str | None = None,
    ) -> None:
        """
        更新发布状态及平台侧 article_id（PRD §PUB-05）。
        调用方负责 commit。
        """
        article = await db.get(Article, article_id)
        if article is None:
            raise ArticleNotFoundException(article_id)
        article.publish_status = status
        if bjh_article_id is not None:
            article.bjh_article_id = bjh_article_id
        if status == PublishStatus.PUBLISHED:
            article.published_at = datetime.now(timezone.utc)

    async def list_articles(
        self,
        db: AsyncSession,
        account_id: int | None = None,
        publish_status: PublishStatus | None = None,
        content_warning: ContentWarning | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Article], int]:
        """
        分页查询文章列表（PRD §6.4.1）。
        通过 task 关联获取 account_id 筛选。
        返回 (items, total)。
        """
        from app.models.task import Task

        stmt = select(Article).join(Task, Article.task_id == Task.id)

        if account_id is not None:
            stmt = stmt.where(Task.account_id == account_id)
        if publish_status is not None:
            stmt = stmt.where(Article.publish_status == publish_status)
        if content_warning is not None:
            stmt = stmt.where(Article.content_warning == content_warning)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Article.created_at.desc()).offset((page - 1) * size).limit(size)
        items = (await db.execute(stmt)).scalars().all()
        return list(items), total

    async def get_article(self, db: AsyncSession, article_id: int) -> Article:
        """获取文章详情（PRD §6.4.2）。不存在时抛 ArticleNotFoundException。"""
        article = await db.get(Article, article_id)
        if article is None:
            raise ArticleNotFoundException(article_id)
        return article

    async def update_article(
        self,
        db: AsyncSession,
        article_id: int,
        title: str,
        body_md: str,
    ) -> Article:
        """
        在线编辑文章（PRD §6.4.3）。
        仅允许编辑 draft 状态文章，自动重算 body_html。
        调用方负责 commit。
        """
        from app.services.bjh_service import BjhService

        article = await db.get(Article, article_id)
        if article is None:
            raise ArticleNotFoundException(article_id)
        if article.publish_status != PublishStatus.DRAFT:
            from app.core.exceptions import AppException
            raise AppException(
                code="ARTICLE_NOT_EDITABLE",
                message=f"仅 draft 状态的文章可编辑，当前状态：{article.publish_status}",
                status_code=409,
            )
        article.title = title
        article.body_md = body_md
        article.body_html = BjhService.md_to_html(body_md)
        return article

    async def manual_publish(
        self,
        db: AsyncSession,
        article_id: int,
        cookie: str,
    ) -> Article:
        """
        人工确认后发布（PRD §6.3.2）。
        partial_content 文章必须先由人工确认（清除 content_warning）才可发布。
        """
        from app.core.constants import CATEGORY_TO_BJH, BJH_CATEGORY_FALLBACK
        from app.services.bjh_service import BjhService

        article = await db.get(Article, article_id)
        if article is None:
            raise ArticleNotFoundException(article_id)
        if article.content_warning is not None:
            raise ArticlePublishBlockedByWarningException()
        if article.publish_status not in (
            PublishStatus.DRAFT,
            PublishStatus.PUBLISH_FAILED,
        ):
            from app.core.exceptions import AppException
            raise AppException(
                code="ARTICLE_NOT_PUBLISHABLE",
                message=f"当前文章状态不可发布：{article.publish_status}",
                status_code=409,
            )

        bjh = BjhService()

        # 标记 publishing
        article.publish_status = PublishStatus.PUBLISHING
        await db.flush()

        edit_token = await bjh.get_edit_token(cookie)

        # 获取分类信息（通过 task）
        from app.models.task import Task
        task = await db.get(Task, article.task_id)
        category = task.category if task else ""
        cate_d1, cate_d2 = CATEGORY_TO_BJH.get(category, BJH_CATEGORY_FALLBACK)

        # 若无 bjh_article_id 则先保存草稿
        if not article.bjh_article_id:
            bjh_aid = await bjh.save_draft(
                cookie, edit_token, article.title, article.body_html
            )
            article.bjh_article_id = bjh_aid

        # 封面图（失败静默）
        cover_url = article.cover_url or ""
        if not cover_url:
            cover_url = await bjh.search_cover(
                cookie, edit_token, article.title[:8], article.bjh_article_id
            ) or ""

        # 正式发布
        result = await bjh.publish_article(
            cookie, edit_token, article.bjh_article_id,
            article.title, article.body_html, cover_url,
            cate_d1, cate_d2,
        )
        if result.get("errno", -1) != 0:
            article.publish_status = PublishStatus.PUBLISH_FAILED
            from app.core.exceptions import AppException
            raise AppException(
                code="PUBLISH_FAILED",
                message=f"发布失败: {result.get('errmsg', 'unknown')}",
                status_code=502,
            )

        article.publish_status = PublishStatus.PUBLISHED
        article.published_at = datetime.now(timezone.utc)
        if cover_url:
            article.cover_url = cover_url
        return article

    async def clear_content_warning(
        self,
        db: AsyncSession,
        article_id: int,
    ) -> Article:
        """
        人工确认清除 content_warning（PRD §10）。
        调用方负责 commit。
        """
        article = await db.get(Article, article_id)
        if article is None:
            raise ArticleNotFoundException(article_id)
        article.content_warning = None
        return article
