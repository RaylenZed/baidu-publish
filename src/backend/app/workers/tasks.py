"""
Celery 异步任务入口（PRD §7.1 执行主流程）。

6 步执行链路：
  Step 1  Prompt 构建（pool_service.sample_combo）
  Step 2  AI 生成初稿（aigc_service.generate_article）
  Step 3  AI 润色（aigc_service.polish_article）
  Step 4  保存草稿（bjh_service.save_draft + article 写库）
  Step 5  搜索封面（bjh_service.search_cover，仅 publish 模式）
  Step 6  正式发布（bjh_service.publish_article，仅 publish 模式）

串行机制：
  执行前获取 Redis 账号锁 account:{account_id}:run_lock（NX EX=task_timeout+60s）。
  锁不可用 → Celery retry countdown=10s，最多重试 3 次。

partial_content 风控：
  AIGC SSE 截断时（PartialContentException）：
  - 跳过润色步骤（若发生在 generate 阶段）
  - task.warning = PARTIAL_CONTENT
  - article.content_warning = PARTIAL_CONTENT
  - 强制以 draft 模式完成（不发布），任务仍标记 SUCCESS

错误分类（task.error_type）：
  AIGC_TIMEOUT / CONNECTION_ERROR / PARSE_ERROR / PUBLISH_FAILED_DRAFT_SAVED / WORKER_CRASH

异步桥接：
  Celery task 为同步函数，通过 asyncio.run() 调用 _async_run_task()。
  DB session 使用独立 NullPool 引擎，避免跨事件循环共用连接。
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import httpx
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.workers.celery_app import celery_app
from app.core.config import settings
from app.core.constants import (
    BJH_CATEGORY_FALLBACK,
    CATEGORY_TO_BJH,
    ContentEventType,
    ContentWarning,
    LogLevel,
    PublishStatus,
    TaskErrorType,
    TaskMode,
    TaskStatus,
    TaskStep,
    TaskWarning,
)
from app.core.logging import get_logger
from app.core.security import decrypt_cookie
from app.models.article import Article
from app.models.task import Task
from app.models.task_log import TaskLog
from app.services.aigc_service import AigcService, PartialContentException
from app.services.audit_service import AuditService
from app.services.bjh_service import BjhService
from app.services.notify_service import NotifyService
from app.services.pool_service import PoolService
from app.utils.cover import build_cover_keywords
from app.ws.task_log_stream import publish_done, publish_log

logger = get_logger(__name__)

_LOCK_BUFFER_SEC = 60  # 账号锁 TTL 超出任务超时的冗余秒数

_aigc = AigcService()
_bjh = BjhService()
_pool = PoolService()
_notify = NotifyService()
_audit = AuditService()


class _NeedRetryError(Exception):
    """账号锁不可用，通知 Celery 延迟重试。"""


# ── Celery Task 入口 ──────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="app.workers.tasks.run_task", max_retries=3)
def run_task(self, task_id: int) -> None:
    """
    同步入口：通过 asyncio.run() 委托给异步流水线。
    锁不可用时触发 Celery retry（countdown=10s）。
    """
    try:
        asyncio.run(_async_run_task(task_id))
    except _NeedRetryError:
        raise self.retry(countdown=10)
    except Exception as exc:
        logger.error(
            "run_task 未处理异常",
            extra={"task_id": task_id, "error": str(exc)},
        )
        raise


# ── 异步流水线主体 ─────────────────────────────────────────────────────────────

async def _async_run_task(task_id: int) -> None:
    """6 步执行流水线（全异步）。"""
    now = datetime.now(timezone.utc)
    account_id: int = 0
    account_name: str = ""
    lock_acquired = False
    # Redis 推送客户端（整个任务生命周期内复用）
    rc_log: aioredis.Redis | None = None

    # ── Phase 0: 加载任务数据（所有 ORM 字段复制为本地变量） ─────────────────
    async with _worker_session() as db:
        task = await db.get(Task, task_id)
        if task is None or task.status != TaskStatus.PENDING:
            return  # 已被处理或已取消

        from app.models.account import Account
        from app.models.system_settings import SystemSettings

        account = await db.get(Account, task.account_id)
        if account is None:
            logger.error(
                "账号不存在，任务跳过",
                extra={"task_id": task_id, "account_id": task.account_id},
            )
            return

        system = await db.get(SystemSettings, 1)

        # 缓存原始值（session 关闭后无法再懒加载）
        account_id = task.account_id
        account_name = account.name
        category = task.category
        mode = task.mode
        topic_keyword = task.topic_keyword
        product_name = task.product_name
        cookie_enc = account.cookie_encrypted

        gen_timeout = getattr(system, "generate_timeout", 240) if system else 240
        pol_timeout = getattr(system, "polish_timeout", 240) if system else 240
        dft_timeout = getattr(system, "draft_timeout", 60) if system else 60
        cvr_timeout = getattr(system, "cover_timeout", 60) if system else 60
        pub_timeout = getattr(system, "publish_timeout", 60) if system else 60
        task_timeout = getattr(system, "task_timeout_minutes", 15) if system else 15
        aigc_model = (
            system.aigc_model.value if system and system.aigc_model else "ds_v3"
        )

    cookie = decrypt_cookie(cookie_enc)

    # ── 获取账号锁 ────────────────────────────────────────────────────────────
    lock_key = f"account:{account_id}:run_lock"
    lock_ttl = task_timeout * 60 + _LOCK_BUFFER_SEC
    rc = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        acquired = await rc.set(lock_key, str(task_id), nx=True, ex=lock_ttl)
    finally:
        await rc.aclose()

    if not acquired:
        logger.info(
            "账号锁被占用，稍后重试",
            extra={"account_id": account_id, "task_id": task_id},
        )
        raise _NeedRetryError()

    lock_acquired = True
    current_step = TaskStep.PROMPT  # 用于异常时记录在哪一步失败
    # 创建 Redis 推送客户端
    rc_log = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    try:
        # ── 标记 RUNNING ─────────────────────────────────────────────────────
        async with _worker_session() as db:
            t = await db.get(Task, task_id)
            t.status = TaskStatus.RUNNING
            t.started_at = now
            t.timeout_at = now + timedelta(minutes=task_timeout)
            await db.commit()

        article_id: int | None = None

        # ── Step 1: PROMPT ────────────────────────────────────────────────────
        current_step = TaskStep.PROMPT
        async with _worker_session() as db:
            combo = await _pool.sample_combo(db, account_id, category)
            t = await db.get(Task, task_id)
            t.combo_id = combo.combo_id
            t.last_step_at = datetime.now(timezone.utc)
            prompt_msg = (
                f"变量组合: combo_id={combo.combo_id} | 角度={combo.angle} | "
                f"人设={combo.persona} | 风格={combo.style} | 结构={combo.structure}"
            )
            _add_log(db, task_id, TaskStep.PROMPT, LogLevel.INFO, prompt_msg)
            await db.commit()
        await _ws_log(rc_log, task_id, TaskStep.PROMPT, LogLevel.INFO, prompt_msg)

        # ── Step 2: GENERATE ──────────────────────────────────────────────────
        current_step = TaskStep.GENERATE
        is_partial = False
        try:
            title_raw, body_raw = await _aigc.generate_article(
                combo, category, topic_keyword, product_name,
                cookie, aigc_model, gen_timeout,
            )
        except PartialContentException as exc:
            title_raw, body_raw = exc.title, exc.body_md
            is_partial = True

        gen_msg = (
            f"初稿生成: 《{title_raw[:20]}》({len(body_raw)} 字)"
            + (" [partial_content]" if is_partial else "")
        )
        async with _worker_session() as db:
            t = await db.get(Task, task_id)
            t.last_step_at = datetime.now(timezone.utc)
            _add_log(db, task_id, TaskStep.GENERATE, LogLevel.INFO, gen_msg)
            await db.commit()
        await _ws_log(rc_log, task_id, TaskStep.GENERATE, LogLevel.INFO, gen_msg)

        # ── Step 3: POLISH ────────────────────────────────────────────────────
        current_step = TaskStep.POLISH
        title, body_md = title_raw, body_raw  # 默认：若润色失败保留初稿

        if not is_partial:
            raw_for_polish = f"标题：{title_raw}\n\n{body_raw}"
            try:
                title, body_md = await _aigc.polish_article(
                    raw_for_polish, category, cookie, aigc_model, pol_timeout,
                )
            except PartialContentException as exc:
                title, body_md = exc.title, exc.body_md
                is_partial = True

        polish_msg = (
            f"润色完成: 《{title[:20]}》({len(body_md)} 字)"
            + (" [partial_content]" if is_partial else "")
        )
        async with _worker_session() as db:
            t = await db.get(Task, task_id)
            t.last_step_at = datetime.now(timezone.utc)
            if is_partial:
                t.warning = TaskWarning.PARTIAL_CONTENT
            _add_log(db, task_id, TaskStep.POLISH, LogLevel.INFO, polish_msg)
            await db.commit()
        await _ws_log(rc_log, task_id, TaskStep.POLISH, LogLevel.INFO, polish_msg)

        # ── Step 4: DRAFT ─────────────────────────────────────────────────────
        current_step = TaskStep.DRAFT
        body_html = BjhService.md_to_html(body_md)
        edit_token = await _bjh.get_edit_token(cookie, timeout=float(dft_timeout))
        bjh_aid = await _bjh.save_draft(
            cookie, edit_token, title, body_html, timeout=float(dft_timeout)
        )

        async with _worker_session() as db:
            article = Article(
                task_id=task_id,
                title=title,
                body_md=body_md,
                body_html=body_html,
                raw_draft=body_raw,
                bjh_article_id=bjh_aid,
                publish_status=PublishStatus.DRAFT,
                content_warning=(ContentWarning.PARTIAL_CONTENT if is_partial else None),
            )
            db.add(article)
            await db.flush()
            article_id = article.id

            t = await db.get(Task, task_id)
            t.last_step_at = datetime.now(timezone.utc)
            draft_msg = f"草稿保存: bjh_article_id={bjh_aid}"
            _add_log(db, task_id, TaskStep.DRAFT, LogLevel.INFO, draft_msg)
            # 记录 combo 使用历史
            await _pool.record_combo(db, account_id, category, combo.combo_id, task_id)
            await db.commit()
        await _ws_log(rc_log, task_id, TaskStep.DRAFT, LogLevel.INFO, draft_msg)

        # partial_content 或 draft 模式 → 直接成功，不进入发布流程
        if is_partial or mode == TaskMode.DRAFT:
            async with _worker_session() as db:
                t = await db.get(Task, task_id)
                t.status = TaskStatus.SUCCESS
                t.finished_at = datetime.now(timezone.utc)
                # 记录任务成功事件（草稿模式）
                await _audit.record_content_event(
                    db,
                    event_type=ContentEventType.TASK_SUCCEEDED.value,
                    account_id=account_id,
                    category=category,
                    task_id=task_id,
                    payload={"combo_id": t.combo_id, "mode": mode.value, "is_partial": is_partial},
                )
                # partial_content 风险通知（NOTIF-03）
                if is_partial and article_id:
                    await _notify.send_content_warning(
                        db, task_id, article_id,
                        warning="partial_content（SSE 截断，内容不完整，需人工确认）",
                    )
                await db.commit()
            await publish_done(rc_log, task_id, TaskStatus.SUCCESS)
            return

        # ── Step 5: COVER ─────────────────────────────────────────────────────
        current_step = TaskStep.COVER
        # 发布前刷新 edit_token
        edit_token = await _bjh.get_edit_token(cookie, timeout=float(cvr_timeout))
        cover_keywords = build_cover_keywords(
            title=title,
            category=category,
            topic_keyword=topic_keyword,
            product_name=product_name,
        )
        cover_url, matched_keyword, attempted_keywords = await _bjh.search_cover_candidates(
            cookie, edit_token, cover_keywords, bjh_aid, timeout=float(cvr_timeout)
        )

        async with _worker_session() as db:
            if article_id:
                art = await db.get(Article, article_id)
                if art:
                    art.cover_url = cover_url
            cover_lvl = LogLevel.INFO if cover_url else LogLevel.WARN
            if cover_url:
                cover_msg = (
                    f"封面图: {cover_url[:80]}（关键词：{matched_keyword or 'unknown'}）"
                )
            else:
                tried = "、".join(attempted_keywords[:6]) or "无"
                cover_msg = f"未找到封面图，已尝试关键词：{tried}"
            t = await db.get(Task, task_id)
            t.last_step_at = datetime.now(timezone.utc)
            _add_log(db, task_id, TaskStep.COVER, cover_lvl, cover_msg)
            await db.commit()
        await _ws_log(rc_log, task_id, TaskStep.COVER, cover_lvl, cover_msg)

        if not cover_url:
            err_msg = (
                "未找到可用封面图，已停止自动发布并保留草稿；"
                f"已尝试关键词：{'、'.join(attempted_keywords[:6]) or '无'}"
            )
            async with _worker_session() as db:
                if article_id:
                    art = await db.get(Article, article_id)
                    if art:
                        art.publish_status = PublishStatus.PUBLISH_FAILED
                    await _audit.record_publish_attempt(
                        db,
                        article_id=article_id,
                        request_summary={
                            "title": title,
                            "bjh_article_id": bjh_aid,
                            "cover_keywords": attempted_keywords,
                        },
                        response_code=None,
                        error_type="cover_not_found",
                        error_message=err_msg[:500],
                    )
                t = await db.get(Task, task_id)
                t.status = TaskStatus.FAILED
                t.error_type = TaskErrorType.PUBLISH_FAILED_DRAFT_SAVED
                t.error_message = err_msg[:500]
                t.finished_at = datetime.now(timezone.utc)
                _add_log(db, task_id, TaskStep.PUBLISH, LogLevel.ERROR, err_msg)
                await _audit.record_content_event(
                    db,
                    event_type=ContentEventType.TASK_FAILED.value,
                    account_id=account_id,
                    category=category,
                    task_id=task_id,
                    payload={
                        "error_type": t.error_type.value,
                        "error_message": err_msg[:200],
                        "cover_keywords": attempted_keywords[:6],
                    },
                )
                await db.commit()
            await _ws_log(rc_log, task_id, TaskStep.PUBLISH, LogLevel.ERROR, err_msg)
            await publish_done(rc_log, task_id, TaskStatus.FAILED)
            await _send_failure_notify(task_id, account_name, err_msg)
            return

        # ── Step 6: PUBLISH ───────────────────────────────────────────────────
        current_step = TaskStep.PUBLISH
        cate_d1, cate_d2 = CATEGORY_TO_BJH.get(category, BJH_CATEGORY_FALLBACK)

        # 标记 PUBLISHING
        async with _worker_session() as db:
            if article_id:
                art = await db.get(Article, article_id)
                if art:
                    art.publish_status = PublishStatus.PUBLISHING
            await db.commit()

        pub_result = await _bjh.publish_article(
            cookie, edit_token, bjh_aid, title, body_html,
            cover_url, cate_d1, cate_d2,
            timeout=float(pub_timeout),
        )

        errno = pub_result.get("errno", -1)
        if errno != 0:
            err_msg = f"发布失败 errno={errno}: {pub_result.get('errmsg', '')}"
            async with _worker_session() as db:
                if article_id:
                    art = await db.get(Article, article_id)
                    if art:
                        art.publish_status = PublishStatus.PUBLISH_FAILED
                    # 记录发布失败审计
                    await _audit.record_publish_attempt(
                        db,
                        article_id=article_id,
                        request_summary={
                            "title": title,
                            "bjh_article_id": bjh_aid,
                            "cover_url": cover_url,
                            "cover_keywords": attempted_keywords[:6],
                        },
                        response_code=errno,
                        error_type=TaskErrorType.PUBLISH_FAILED_DRAFT_SAVED.value,
                        error_message=err_msg[:500],
                    )
                t = await db.get(Task, task_id)
                t.status = TaskStatus.FAILED
                t.error_type = TaskErrorType.PUBLISH_FAILED_DRAFT_SAVED
                t.error_message = err_msg[:500]
                t.finished_at = datetime.now(timezone.utc)
                _add_log(db, task_id, TaskStep.PUBLISH, LogLevel.ERROR, err_msg)
                # 记录任务失败事件
                await _audit.record_content_event(
                    db,
                    event_type=ContentEventType.TASK_FAILED.value,
                    account_id=account_id,
                    category=category,
                    task_id=task_id,
                    payload={"error_type": t.error_type.value, "error_message": err_msg[:200]},
                )
                await db.commit()
            await _ws_log(rc_log, task_id, TaskStep.PUBLISH, LogLevel.ERROR, err_msg)
            await publish_done(rc_log, task_id, TaskStatus.FAILED)
            await _send_failure_notify(task_id, account_name, err_msg)
            return

        # 发布成功
        nid = pub_result.get("ret", {}).get("nid", "")
        pub_msg = f"发布成功! nid={nid}"
        async with _worker_session() as db:
            if article_id:
                art = await db.get(Article, article_id)
                if art:
                    art.publish_status = PublishStatus.PUBLISHED
                    art.published_at = datetime.now(timezone.utc)
                # 记录发布成功审计
                await _audit.record_publish_attempt(
                    db,
                    article_id=article_id,
                    request_summary={
                        "title": title,
                        "bjh_article_id": bjh_aid,
                        "cover_url": cover_url,
                        "cover_keywords": attempted_keywords[:6],
                    },
                    response_code=0,
                    error_type=None,
                    error_message=None,
                )
                # 记录文章发布事件
                await _audit.record_content_event(
                    db,
                    event_type=ContentEventType.ARTICLE_PUBLISHED.value,
                    account_id=account_id,
                    category=category,
                    task_id=task_id,
                    payload={"nid": nid, "bjh_article_id": bjh_aid},
                )
            t = await db.get(Task, task_id)
            t.status = TaskStatus.SUCCESS
            t.finished_at = datetime.now(timezone.utc)
            t.last_step_at = datetime.now(timezone.utc)
            _add_log(db, task_id, TaskStep.PUBLISH, LogLevel.INFO, pub_msg)
            # 记录任务成功事件
            await _audit.record_content_event(
                db,
                event_type=ContentEventType.TASK_SUCCEEDED.value,
                account_id=account_id,
                category=category,
                task_id=task_id,
                payload={"combo_id": t.combo_id},
            )
            await db.commit()
        await _ws_log(rc_log, task_id, TaskStep.PUBLISH, LogLevel.INFO, pub_msg)
        await publish_done(rc_log, task_id, TaskStatus.SUCCESS)

    except _NeedRetryError:
        raise

    except Exception as exc:
        error_type = _classify_error(exc)
        error_msg = str(exc)[:500]
        logger.error(
            "任务执行失败",
            extra={
                "task_id": task_id,
                "step": current_step.value,
                "error_type": error_type.value,
                "error": error_msg,
            },
        )
        fail_msg = f"任务执行失败: {error_msg}"
        try:
            async with _worker_session() as db:
                t = await db.get(Task, task_id)
                if t and t.status == TaskStatus.RUNNING:
                    t.status = TaskStatus.FAILED
                    t.error_type = error_type
                    t.error_message = error_msg
                    t.finished_at = datetime.now(timezone.utc)
                    _add_log(db, task_id, current_step, LogLevel.ERROR, fail_msg)
                    # 记录任务失败事件
                    await _audit.record_content_event(
                        db,
                        event_type=ContentEventType.TASK_FAILED.value,
                        account_id=account_id,
                        category=category,
                        task_id=task_id,
                        payload={
                            "error_type": error_type.value,
                            "error_message": error_msg[:200],
                            "step": current_step.value,
                        },
                    )
                    await db.commit()
        except Exception:
            pass
        try:
            if rc_log:
                await _ws_log(rc_log, task_id, current_step, LogLevel.ERROR, fail_msg)
                await publish_done(rc_log, task_id, TaskStatus.FAILED)
        except Exception:
            pass
        await _send_failure_notify(task_id, account_name, error_msg)

    finally:
        if lock_acquired:
            await _release_lock(account_id, task_id)
        if rc_log:
            try:
                await rc_log.aclose()
            except Exception:
                pass


# ── 工具函数 ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def _worker_session() -> AsyncGenerator[AsyncSession, None]:
    """
    创建独立 NullPool 引擎和 Session。
    每次 asyncio.run() 创建新事件循环，NullPool 避免跨事件循环复用连接。
    """
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    finally:
        await engine.dispose()


def _add_log(
    db: AsyncSession,
    task_id: int,
    step: TaskStep,
    level: LogLevel,
    message: str,
) -> None:
    """向 DB session 添加 TaskLog 记录（调用方负责 commit）。"""
    db.add(TaskLog(task_id=task_id, step=step, level=level, message=message))


async def _release_lock(account_id: int, task_id: int) -> None:
    """释放 Redis 账号锁（仅当锁仍属于本任务时）。"""
    lock_key = f"account:{account_id}:run_lock"
    rc = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        current = await rc.get(lock_key)
        if current == str(task_id):
            await rc.delete(lock_key)
    except Exception as exc:
        logger.warning("账号锁释放失败", extra={"error": str(exc)})
    finally:
        await rc.aclose()


async def _send_failure_notify(
    task_id: int, account_name: str, error_msg: str
) -> None:
    """发送任务失败企微通知（非阻塞，异常静默）。"""
    try:
        async with _worker_session() as db:
            await _notify.send_task_failure(db, task_id, account_name, error_msg)
    except Exception:
        pass


def _classify_error(exc: Exception) -> TaskErrorType:
    """将异常映射到 TaskErrorType 枚举。"""
    if isinstance(exc, httpx.TimeoutException):
        return TaskErrorType.AIGC_TIMEOUT
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return TaskErrorType.CONNECTION_ERROR
    if isinstance(exc, (json.JSONDecodeError, KeyError, ValueError)):
        return TaskErrorType.PARSE_ERROR
    return TaskErrorType.WORKER_CRASH


async def _ws_log(
    rc: aioredis.Redis,
    task_id: int,
    step: TaskStep,
    level: LogLevel,
    message: str,
) -> None:
    """发布日志事件到 Redis Pub/Sub（异常静默）。"""
    try:
        await publish_log(
            rc, task_id,
            step=step.value,
            level=level.value,
            message=message,
            ts=datetime.now(timezone.utc).isoformat(),
        )
    except Exception:
        pass
