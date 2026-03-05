"""
Celery Beat 定期作业（PRD §TASK-10 / PRD §TASK-11 / PRD §8.2 / PRD §NOTIF-02）。

  recover_timeout_tasks  每 2 分钟扫描 running/pending 任务，超时转 timeout
  fire_schedules        每分钟触发启用中的定时任务
  recover_misfire       每 5 分钟补执行 24 小时内的 misfire
  send_daily_summary    每日 22:00（上海时间）发送任务汇总通知
"""

from __future__ import annotations

import asyncio

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.workers.beat_jobs.recover_timeout_tasks")
def recover_timeout_tasks() -> None:
    """
    扫描 timeout_at < NOW() 的 running/pending 任务，标记为 timeout（PRD §TASK-10）。
    由 Beat 每 2 分钟触发（见 celery_app.py beat_schedule）。
    """
    count = asyncio.run(_async_recover_timeout())
    if count > 0:
        logger.info("超时任务回收完成", extra={"count": count})


async def _async_recover_timeout() -> int:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import settings
    from app.services.task_service import TaskService

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as db:
            count = await TaskService().recover_timeout_tasks(db)
            await db.commit()
            return count
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.beat_jobs.fire_schedules")
def fire_schedules() -> None:
    """
    触发已到时的定时任务（PRD §TASK-11）。
    由 Beat 每 1 分钟触发，检查 next_fire_at <= NOW()。
    """
    count = asyncio.run(_async_fire_schedules())
    if count > 0:
        logger.info("定时任务触发完成", extra={"count": count})


async def _async_fire_schedules() -> int:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import settings
    from app.services.schedule_service import ScheduleService

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as db:
            count = await ScheduleService().fire_enabled_schedules(db)
            return count
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.beat_jobs.recover_misfire")
def recover_misfire() -> None:
    """
    Misfire 补执行（PRD §TASK-11）。
    系统重启后补执行 24 小时内错过的触发。
    由 Beat 每 5 分钟触发。
    """
    count = asyncio.run(_async_recover_misfire())
    if count > 0:
        logger.info("Misfire 补执行完成", extra={"count": count})


async def _async_recover_misfire() -> int:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import settings
    from app.services.schedule_service import ScheduleService

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as db:
            # 先推进陈旧调度（避免永久饿死）
            await ScheduleService().advance_stale_schedules(db)
            # 再执行 misfire 补执行
            count = await ScheduleService().recover_misfire(db)
            return count
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.beat_jobs.advance_stale_schedules")
def advance_stale_schedules() -> None:
    """
    推进陈旧调度的 next_fire_at 到未来触发点。
    由 Beat 每 5 分钟触发，与 recover_misfire 配合使用。
    """
    count = asyncio.run(_async_advance_stale_schedules())
    if count > 0:
        logger.info("陈旧调度已推进", extra={"count": count})


async def _async_advance_stale_schedules() -> int:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import settings
    from app.services.schedule_service import ScheduleService

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as db:
            count = await ScheduleService().advance_stale_schedules(db)
            return count
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.beat_jobs.send_daily_summary")
def send_daily_summary() -> None:
    """
    每日 22:00（上海时间）发送任务汇总通知（PRD §NOTIF-02）。
    统计当日 Asia/Shanghai 自然日内的任务状态分布及发布数量。
    """
    asyncio.run(_async_send_daily_summary())


async def _async_send_daily_summary() -> None:
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import settings
    from app.core.constants import TaskStatus, PublishStatus
    from app.models.task import Task
    from app.models.article import Article
    from app.services.notify_service import NotifyService

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as db:
            tz_sh = ZoneInfo("Asia/Shanghai")
            now_sh = datetime.now(tz_sh)
            today_start_sh = now_sh.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_utc = today_start_sh.astimezone(timezone.utc)

            # 今日各状态任务数
            rows = (await db.execute(
                select(Task.status, func.count(Task.id).label("cnt"))
                .where(Task.created_at >= today_start_utc)
                .group_by(Task.status)
            )).all()

            status_counts: dict[str, int] = {row[0]: row[1] for row in rows}
            total = sum(status_counts.values())
            success = status_counts.get(TaskStatus.SUCCESS, 0)
            failed = status_counts.get(TaskStatus.FAILED, 0)
            timeout = status_counts.get(TaskStatus.TIMEOUT, 0)

            # 今日已发布文章数
            published = (await db.scalar(
                select(func.count(Article.id)).where(
                    Article.publish_status == PublishStatus.PUBLISHED,
                    Article.published_at >= today_start_utc,
                )
            )) or 0

            stats = {
                "total": total,
                "success": success,
                "failed": failed,
                "timeout": timeout,
                "published": published,
            }
            await NotifyService().send_daily_summary(db, stats)
    except Exception as exc:
        logger.error("每日汇总通知发送失败", extra={"error": str(exc)})
    finally:
        await engine.dispose()