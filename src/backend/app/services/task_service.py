"""
任务编排服务（PRD §TASK-01~11 / PRD §5.2 任务执行流程）

职责：
  - 幂等创建任务（Redis idempotency_key 5 分钟去重 + DB 兜底）
  - 同账号 60 秒同品类同模式防重（TaskDuplicateException）
  - 连续失败 3 次冷却 30 分钟（TaskCoolingDownException）
  - 单账号每日限额检查（TaskDailyLimitExceededException）
  - 状态机推进（由 Worker 调用）
  - 任务取消（pending → canceled）
  - 重试（创建新任务，retry_of_task_id 追踪）
  - 强制草稿（force-draft，创建 mode=draft 的新任务）
  - 超时任务回收（Beat 2 分钟轮询）
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    CookieStatus,
    TaskMode,
    TaskStatus,
    TaskErrorType,
)
from app.core.exceptions import (
    AccountCookieExpiredException,
    AccountNotFoundException,
    TaskCoolingDownException,
    TaskDailyLimitExceededException,
    TaskDuplicateException,
    TaskIdempotencyConflictException,
    TaskInvalidStatusException,
    TaskNotFoundException,
    ValidationException,
)
from app.models.account import Account
from app.models.task import Task
from app.models.task_log import TaskLog

# Redis key 前缀
_IDEMPOTENCY_PREFIX = "idempotency:"
_IDEMPOTENCY_TTL = 300       # 5 分钟
_DEDUP_WINDOW_SEC = 60       # 同账号同品类同模式防重窗口
_COOLDOWN_WINDOW_MIN = 30    # 连续失败冷却时间（分钟）
_COOLDOWN_FAILURE_THRESHOLD = 3


class TaskService:
    """任务生命周期管理。"""

    # ── 创建 ─────────────────────────────────────────────────────────────────

    async def create_task(
        self,
        db: AsyncSession,
        account_id: int,
        category: str,
        mode: TaskMode,
        topic_keyword: str | None,
        product_name: str | None,
        idempotency_key: str | None,
        schedule_id: int | None = None,
        retry_of_task_id: int | None = None,
    ) -> Task:
        """
        创建任务，含完整的幂等/防重/限额校验流程（PRD §TASK-01~04）。

        校验顺序：
          1. 账号存在且 Cookie 未过期
          2. 品类与账号绑定的品类一致
          3. 幂等 key 去重（Redis 5 分钟）
          4. 同账号 60 秒同品类同模式防重
          5. 连续失败冷却（3 次/30 分钟）
          6. 每日限额
        """
        # 1. 账号检查
        account = await db.get(Account, account_id)
        if account is None:
            raise AccountNotFoundException(account_id)
        if account.cookie_status == CookieStatus.EXPIRED:
            raise AccountCookieExpiredException(account_id)

        # 2. 品类处理：留空时随机选择账号绑定品类（PRD：category 可留空）
        bound_categories = account.categories or []
        if not category:
            if not bound_categories:
                raise ValidationException(f"账号「{account.name}」未绑定任何品类，无法随机选择")
            category = random.choice(bound_categories)
        elif category not in bound_categories:
            raise ValidationException(
                f"账号「{account.name}」未绑定品类「{category}」，"
                f"已绑定品类：{bound_categories}"
            )

        # 3. 幂等 key 原子占位（SET NX EX，宪法 §3 #3）
        #    _check_idempotency 内部 SET NX 成功→返回 None（可继续创建）
        #    SET NX 失败且已有任务→返回已有任务
        #    SET NX 失败且"pending"→抛 TaskIdempotencyConflictException
        if idempotency_key:
            existing = await self._check_idempotency(db, idempotency_key)
            if existing is not None:
                return existing

        # 4. 60 秒防重
        await self._check_dedup(db, account_id, category, mode)

        # 5. 冷却检查
        await self._check_cooldown(db, account_id)

        # 6. 每日限额检查
        await self._check_daily_limit(db, account_id)

        # 创建任务；若失败则释放幂等占位，允许后续重试
        now = datetime.now(timezone.utc)
        task = Task(
            account_id=account_id,
            schedule_id=schedule_id,
            retry_of_task_id=retry_of_task_id,
            category=category,
            mode=mode,
            topic_keyword=topic_keyword,
            product_name=product_name,
            idempotency_key=idempotency_key,
            status=TaskStatus.PENDING,
            created_at=now,
        )
        db.add(task)
        try:
            await db.flush()
            await db.refresh(task)
        except Exception:
            if idempotency_key:
                await self._release_idempotency(idempotency_key)
            raise

        # 写入 task_created 审计事件（PRD §3 #12）
        from app.services.audit_service import AuditService
        from app.core.constants import ContentEventType
        await AuditService().record_content_event(
            db,
            event_type=ContentEventType.TASK_CREATED.value,
            account_id=account_id,
            category=category,
            task_id=task.id,
        )

        # 将占位 "pending" 更新为真实 task_id
        if idempotency_key:
            await self._store_idempotency(idempotency_key, task.id)

        # 派发 Celery 任务
        self._dispatch(task.id)

        return task

    # ── 查询 ─────────────────────────────────────────────────────────────────

    async def get_task(self, db: AsyncSession, task_id: int) -> Task:
        task = await db.get(Task, task_id)
        if task is None:
            raise TaskNotFoundException(task_id)
        return task

    async def list_tasks(
        self,
        db: AsyncSession,
        *,
        status: TaskStatus | None = None,
        account_id: int | None = None,
        category: str | None = None,
        mode: TaskMode | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Task], int]:
        """返回 (items, total)，调用方负责构造 PageData。"""
        conditions = []
        if status is not None:
            conditions.append(Task.status == status)
        if account_id is not None:
            conditions.append(Task.account_id == account_id)
        if category is not None:
            conditions.append(Task.category == category)
        if mode is not None:
            conditions.append(Task.mode == mode)
        if date_from is not None:
            conditions.append(Task.created_at >= date_from)
        if date_to is not None:
            conditions.append(Task.created_at <= date_to)

        where = and_(*conditions) if conditions else True

        total = await db.scalar(select(func.count()).select_from(Task).where(where)) or 0
        result = await db.execute(
            select(Task)
            .where(where)
            .order_by(Task.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), total

    async def get_task_logs(self, db: AsyncSession, task_id: int) -> list[TaskLog]:
        """获取任务的历史日志列表（非实时，实时日志走 WebSocket）。"""
        await self.get_task(db, task_id)  # 验证任务存在
        result = await db.execute(
            select(TaskLog)
            .where(TaskLog.task_id == task_id)
            .order_by(TaskLog.created_at.asc())
        )
        return list(result.scalars().all())

    # ── 状态操作 ──────────────────────────────────────────────────────────────

    async def cancel_task(self, db: AsyncSession, task_id: int) -> Task:
        """取消 pending 任务（PRD §TASK-06）。仅 pending 状态可取消。"""
        task = await self.get_task(db, task_id)
        if task.status != TaskStatus.PENDING:
            raise TaskInvalidStatusException(task_id, task.status.value, "pending")
        task.status = TaskStatus.CANCELED
        await db.flush()
        return task

    async def retry_task(self, db: AsyncSession, task_id: int) -> Task:
        """
        重试失败/超时任务（PRD §TASK-05）。
        创建新任务，原任务保持 failed/timeout 状态，通过 retry_of_task_id 追踪链路。
        """
        original = await self.get_task(db, task_id)
        if original.status not in (TaskStatus.FAILED, TaskStatus.TIMEOUT):
            raise TaskInvalidStatusException(
                task_id, original.status.value, "failed 或 timeout"
            )

        return await self.create_task(
            db,
            account_id=original.account_id,
            category=original.category,
            mode=original.mode,
            topic_keyword=original.topic_keyword,
            product_name=original.product_name,
            idempotency_key=None,
            schedule_id=original.schedule_id,
            retry_of_task_id=task_id,  # 追踪重试链路
        )

    async def force_draft(self, db: AsyncSession, task_id: int) -> Task:
        """
        强制转草稿模式重跑（PRD §TASK-08）。
        创建一个 mode=draft 的重试任务，跳过发布步骤，仅保存草稿。
        """
        original = await self.get_task(db, task_id)
        if original.status not in (TaskStatus.FAILED, TaskStatus.TIMEOUT, TaskStatus.RUNNING):
            raise TaskInvalidStatusException(
                task_id, original.status.value, "failed / timeout / running"
            )

        return await self.create_task(
            db,
            account_id=original.account_id,
            category=original.category,
            mode=TaskMode.DRAFT,
            topic_keyword=original.topic_keyword,
            product_name=original.product_name,
            idempotency_key=None,
            schedule_id=original.schedule_id,
        )

    async def retry_all_failed(self, db: AsyncSession) -> list[Task]:
        """批量重试所有 failed/timeout 状态的任务。"""
        result = await db.execute(
            select(Task).where(
                Task.status.in_([TaskStatus.FAILED, TaskStatus.TIMEOUT])
            ).order_by(Task.created_at.desc())
        )
        tasks = list(result.scalars().all())
        created: list[Task] = []
        for t in tasks:
            try:
                new_task = await self.retry_task(db, t.id)
                created.append(new_task)
            except Exception:
                pass  # 单个失败不中断整体
        return created

    # ── 超时回收（Beat 调用）────────────────────────────────────────────────────

    async def recover_timeout_tasks(self, db: AsyncSession) -> int:
        """
        扫描并回收超时任务（PRD §TASK-10）。
        被 Beat beat_jobs.py 每 2 分钟调用一次。
        返回回收的任务数量。
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Task).where(
                and_(
                    Task.status.in_([TaskStatus.RUNNING, TaskStatus.PENDING]),
                    Task.timeout_at.isnot(None),
                    Task.timeout_at < now,
                )
            )
        )
        timeout_tasks = list(result.scalars().all())

        for task in timeout_tasks:
            task.status = TaskStatus.TIMEOUT
            task.error_type = TaskErrorType.TIMEOUT
            task.finished_at = now

        if timeout_tasks:
            await db.flush()

        return len(timeout_tasks)

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    # 占位标记，表示当前有请求正在创建任务
    _IDEMPOTENCY_PENDING = "pending"

    async def _check_idempotency(
        self, db: AsyncSession, idempotency_key: str
    ) -> Task | None:
        """
        原子幂等占位（SET NX EX）——宪法 §3 #3 要求。

        流程：
        1. SET NX EX "pending"：
           - 成功（返回 True）→ 本请求首次占位，允许创建任务，返回 None
           - 失败（返回 False）→ key 已存在（另一请求占位或已有任务）
        2. 失败时 GET 当前值：
           - 是 task_id（数字）→ 读出已有任务返回（幂等成功）
           - 是 "pending"    → 并发竞争，抛 TaskIdempotencyConflictException
           - 不存在（极短窗口过期）→ DB 兜底查询
        """
        redis_key = f"{_IDEMPOTENCY_PREFIX}{idempotency_key}"
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            acquired = await client.set(
                redis_key, self._IDEMPOTENCY_PENDING,
                ex=_IDEMPOTENCY_TTL, nx=True,
            )
            if acquired:
                return None  # 占位成功，允许继续创建

            existing_val = await client.get(redis_key)
        finally:
            await client.aclose()

        if existing_val and existing_val != self._IDEMPOTENCY_PENDING:
            # 已有真实 task_id
            task = await db.get(Task, int(existing_val))
            if task:
                return task

        if existing_val == self._IDEMPOTENCY_PENDING:
            # 并发竞争：另一请求正在创建
            raise TaskIdempotencyConflictException(idempotency_key)

        # DB 兜底（Redis 重启、key 在读取间隙过期）
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=_IDEMPOTENCY_TTL)
        task = await db.scalar(
            select(Task).where(
                and_(
                    Task.idempotency_key == idempotency_key,
                    Task.created_at >= cutoff,
                )
            )
        )
        return task

    async def _store_idempotency(self, idempotency_key: str, task_id: int) -> None:
        """创建成功后，将占位 'pending' 更新为真实 task_id。"""
        redis_key = f"{_IDEMPOTENCY_PREFIX}{idempotency_key}"
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await client.set(redis_key, str(task_id), ex=_IDEMPOTENCY_TTL)
        finally:
            await client.aclose()

    async def _release_idempotency(self, idempotency_key: str) -> None:
        """任务创建失败时，释放占位 key，避免 TTL 内阻塞重试。"""
        redis_key = f"{_IDEMPOTENCY_PREFIX}{idempotency_key}"
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await client.delete(redis_key)
        finally:
            await client.aclose()

    async def _check_dedup(
        self,
        db: AsyncSession,
        account_id: int,
        category: str,
        mode: TaskMode,
    ) -> None:
        """60 秒内同账号同品类同模式防重（TASK-03）。"""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=_DEDUP_WINDOW_SEC)
        count = await db.scalar(
            select(func.count()).select_from(Task).where(
                and_(
                    Task.account_id == account_id,
                    Task.category == category,
                    Task.mode == mode,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                    Task.created_at >= cutoff,
                )
            )
        )
        if count and count > 0:
            raise TaskDuplicateException()

    async def _check_cooldown(self, db: AsyncSession, account_id: int) -> None:
        """
        最近 3 条完成任务连续失败 → 冷却 30 分钟（TASK-08）。
        取该账号最近 3 条已完成任务（success/failed/timeout），
        若全部为 failed/timeout 且最后一条 finished_at 在 30 分钟内，则触发冷却。
        """
        result = await db.execute(
            select(Task.status, Task.finished_at)
            .where(
                and_(
                    Task.account_id == account_id,
                    Task.status.in_([
                        TaskStatus.FAILED,
                        TaskStatus.TIMEOUT,
                        TaskStatus.SUCCESS,
                    ]),
                )
            )
            .order_by(Task.created_at.desc())
            .limit(_COOLDOWN_FAILURE_THRESHOLD)
        )
        recent = result.fetchall()
        if len(recent) < _COOLDOWN_FAILURE_THRESHOLD:
            return  # 历史不足 3 条，不触发冷却

        all_failed = all(
            row.status in (TaskStatus.FAILED, TaskStatus.TIMEOUT) for row in recent
        )
        if not all_failed:
            return

        last_finished = recent[0].finished_at
        if last_finished is None:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=_COOLDOWN_WINDOW_MIN)
        # finished_at 存储为 UTC，兼容有无 tzinfo
        if last_finished.tzinfo is None:
            last_finished = last_finished.replace(tzinfo=timezone.utc)
        if last_finished >= cutoff:
            raise TaskCoolingDownException(account_id)

    async def _check_daily_limit(self, db: AsyncSession, account_id: int) -> None:
        """检查单账号每日执行上限（按上海时区自然日计算，PRD §TASK-03）。"""
        from datetime import timezone
        import pytz
        from app.models.system_settings import SystemSettings

        system = await db.get(SystemSettings, 1)
        daily_limit = system.daily_limit if system else 3  # 兜底默认值

        # 按上海时区计算"今日"起始时间，保留时区信息（aware），与 TIMESTAMPTZ 字段直接比较
        sh_tz = pytz.timezone("Asia/Shanghai")
        today_sh = datetime.now(sh_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_sh.astimezone(timezone.utc)

        count = await db.scalar(
            select(func.count()).select_from(Task).where(
                and_(
                    Task.account_id == account_id,
                    Task.status.not_in([TaskStatus.CANCELED]),
                    Task.created_at >= today_start_utc,
                )
            )
        )
        if count and count >= daily_limit:
            raise TaskDailyLimitExceededException(account_id, daily_limit)

    def _dispatch(self, task_id: int) -> None:
        """派发任务到 Celery Worker（fire-and-forget）。"""
        try:
            from app.workers.tasks import run_task
            run_task.delay(task_id)
        except Exception:
            # Worker 不可用时不阻塞任务创建，任务留在 pending 状态等 Beat 扫描
            pass
