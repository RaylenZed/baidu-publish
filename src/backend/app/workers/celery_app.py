"""
Celery 应用配置（PRD §13 任务队列）。

Worker 启动命令：
  celery -A app.workers.celery_app worker --loglevel=info --concurrency=3

Beat 启动命令：
  celery -A app.workers.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "bjh_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks",
        "app.workers.beat_jobs",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_acks_late=True,           # Worker 崩溃时任务重新入队
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # 防止任务囤积
    beat_schedule={
        # 每 2 分钟扫描超时任务（TASK-10）
        "timeout-recovery": {
            "task": "app.workers.beat_jobs.recover_timeout_tasks",
            "schedule": 120,
        },
        # 每 1 分钟触发已到时的定时任务（TASK-11）
        "fire-schedules": {
            "task": "app.workers.beat_jobs.fire_schedules",
            "schedule": 60,
        },
        # 每 5 分钟补执行 24 小时内的 misfire（TASK-11）
        "misfire-recovery": {
            "task": "app.workers.beat_jobs.recover_misfire",
            "schedule": 300,
        },
        # 每日 22:00（上海时间）发送汇总通知（NOTIF-02）
        "daily-summary": {
            "task": "app.workers.beat_jobs.send_daily_summary",
            "schedule": crontab(hour=22, minute=0),
        },
    },
)
