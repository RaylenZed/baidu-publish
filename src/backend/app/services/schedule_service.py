"""
定时任务服务（PRD §6.3.5 / §11.6 / PRD §TASK-11）

职责：
  - CRUD（创建、列表、编辑、删除、启停）
  - Cron 计算 next_fire_at
  - 触发执行 fire()（创建任务，调用 task_service）
  - Misfire 补偿（Celery Beat 触发 fire_schedules）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from typing import List

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.account import Account
from app.models.schedule import Schedule, ScheduleAccount
from app.models.task import Task
from app.services.task_service import TaskService


class ScheduleService:
    """定时任务管理。"""

    # Misfire 容忍时间（24 小时）
    _MISFIRE_THRESHOLD_HOURS = 24

    async def list_schedules(
        self,
        db: AsyncSession,
        enabled: bool | None = None,
    ) -> list[Schedule]:
        """查询所有定时任务。"""
        stmt = select(Schedule).order_by(Schedule.created_at.desc())
        if enabled is not None:
            stmt = stmt.where(Schedule.enabled == enabled)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_schedule(
        self,
        db: AsyncSession,
        schedule_id: int,
    ) -> Schedule:
        """获取定时任务详情（含关联账号）。"""
        schedule = await db.get(Schedule, schedule_id)
        if schedule is None:
            raise AppException(
                code="SCHEDULE_NOT_FOUND",
                message=f"定时任务 {schedule_id} 不存在",
                status_code=404,
            )
        return schedule

    async def get_schedule_detail(
        self,
        db: AsyncSession,
        schedule_id: int,
    ) -> tuple[Schedule, list[dict]]:
        """获取定时任务详情及关联账号信息。"""
        schedule = await self.get_schedule(db, schedule_id)
        stmt = (
            select(Account.id, Account.name)
            .join(ScheduleAccount, ScheduleAccount.account_id == Account.id)
            .where(ScheduleAccount.schedule_id == schedule_id)
        )
        result = await db.execute(stmt)
        accounts = [
            {"account_id": row[0], "account_name": row[1]}
            for row in result.fetchall()
        ]
        return schedule, accounts

    async def create_schedule(
        self,
        db: AsyncSession,
        name: str,
        cron_expr: str,
        mode: str,
        timezone: str,
        account_ids: list[int],
        topic_keyword: str | None = None,
        product_name: str | None = None,
    ) -> Schedule:
        """创建定时任务。"""
        # 验证 cron 表达式
        if not self._validate_cron(cron_expr, timezone):
            raise AppException(
                code="INVALID_CRON",
                message=f"无效的 cron 表达式: {cron_expr}",
                status_code=400,
            )
        # 验证账号存在
        if account_ids:
            stmt = select(Account).where(Account.id.in_(account_ids))
            result = await db.execute(stmt)
            found_ids = {a.id for a in result.scalars().all()}
            missing = set(account_ids) - found_ids
            if missing:
                raise AppException(
                    code="ACCOUNT_NOT_FOUND",
                    message=f"账号不存在: {missing}",
                    status_code=404,
                )

        next_fire = self._calc_next_fire(cron_expr, timezone)

        schedule = Schedule(
            name=name,
            cron_expr=cron_expr,
            mode=mode,
            timezone=timezone,
            enabled=True,
            next_fire_at=next_fire,
        )
        db.add(schedule)
        await db.flush()
        await db.refresh(schedule)

        # 关联账号
        for aid in account_ids:
            db.add(ScheduleAccount(schedule_id=schedule.id, account_id=aid))

        return schedule

    async def update_schedule(
        self,
        db: AsyncSession,
        schedule_id: int,
        name: str | None,
        cron_expr: str | None,
        mode: str | None,
        timezone: str | None,
        account_ids: list[int] | None,
        topic_keyword: str | None,
        product_name: str | None,
    ) -> Schedule:
        """编辑定时任务。"""
        schedule = await self.get_schedule(db, schedule_id)

        if name is not None:
            schedule.name = name
        if mode is not None:
            schedule.mode = mode
        if timezone is not None:
            schedule.timezone = timezone
        if cron_expr is not None:
            if not self._validate_cron(cron_expr, schedule.timezone):
                raise AppException(
                    code="INVALID_CRON",
                    message=f"无效的 cron 表达式: {cron_expr}",
                    status_code=400,
                )
            schedule.cron_expr = cron_expr
            schedule.next_fire_at = self._calc_next_fire(cron_expr, schedule.timezone)

        if account_ids is not None:
            # 验证账号
            if account_ids:
                stmt = select(Account).where(Account.id.in_(account_ids))
                result = await db.execute(stmt)
                found_ids = {a.id for a in result.scalars().all()}
                missing = set(account_ids) - found_ids
                if missing:
                    raise AppException(
                        code="ACCOUNT_NOT_FOUND",
                        message=f"账号不存在: {missing}",
                        status_code=404,
                    )
            # 重建关联（先删后增）
            await db.execute(
                ScheduleAccount.__table__.delete().where(
                    ScheduleAccount.schedule_id == schedule_id
                )
            )
            for aid in account_ids:
                db.add(ScheduleAccount(schedule_id=schedule_id, account_id=aid))

        return schedule

    async def delete_schedule(
        self,
        db: AsyncSession,
        schedule_id: int,
    ) -> None:
        """删除定时任务（CASCADE 清理关联）。"""
        schedule = await self.get_schedule(db, schedule_id)
        await db.delete(schedule)

    async def toggle_schedule(
        self,
        db: AsyncSession,
        schedule_id: int,
    ) -> Schedule:
        """切换启用/禁用状态。"""
        schedule = await self.get_schedule(db, schedule_id)
        schedule.enabled = not schedule.enabled
        if schedule.enabled and schedule.next_fire_at is None:
            schedule.next_fire_at = self._calc_next_fire(
                schedule.cron_expr, schedule.timezone
            )
        return schedule

    async def fire(self, db: AsyncSession, schedule_id: int) -> list[Task]:
        """
        触发定时任务，为每个关联账号创建一个任务。
        更新 last_fired_at / next_fire_at。
        返回创建的任务列表。
        """
        schedule = await self.get_schedule(db, schedule_id)
        if not schedule.enabled:
            return []

        now = datetime.now(dt_timezone.utc)

        # 获取关联账号及绑定品类
        stmt = select(Account.id, Account.categories).join(ScheduleAccount).where(
            ScheduleAccount.schedule_id == schedule_id
        )
        result = await db.execute(stmt)
        account_rows = result.fetchall()

        task_svc = TaskService()
        created_tasks: list[Task] = []

        for account_id, categories in account_rows:
            # 从账号绑定的品类中随机选择一个
            import random
            category = random.choice(categories) if categories else ""
            task = await task_svc.create_task(
                db,
                account_id=account_id,
                category=category,
                mode=schedule.mode,
                topic_keyword=None,
                product_name=None,
                idempotency_key=None,
                schedule_id=schedule_id,
            )
            created_tasks.append(task)

        # 更新触发时间
        schedule.last_fired_at = now
        schedule.next_fire_at = self._calc_next_fire(
            schedule.cron_expr, schedule.timezone
        )

        return created_tasks

    async def fire_enabled_schedules(self, db: AsyncSession) -> int:
        """
        Celery Beat 调用：触发所有已到时的启用中定时任务。
        检查 next_fire_at <= NOW()，但排除超过 24 小时的旧触发（与 misfire 策略对齐）。
        返回触发成功的任务数量。
        """
        now = datetime.now(dt_timezone.utc)
        threshold = now - timedelta(hours=self._MISFIRE_THRESHOLD_HOURS)

        # 仅触发 24 小时窗口内的调度，避免对太久以前的触发进行重复执行
        stmt = select(Schedule).where(
            Schedule.enabled == True,  # noqa: E712
            Schedule.next_fire_at >= threshold,  # 排除 >24h 的旧触发
            Schedule.next_fire_at <= now,
        )
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        count = 0
        for sch in schedules:
            try:
                await self.fire(db, sch.id)
                await db.commit()
                count += 1
            except Exception:
                pass  # 单个失败不阻断其他

        return count

    async def recover_misfire(self, db: AsyncSession) -> int:
        """
        Misfire 补偿（PRD §TASK-11）。
        补执行 24 小时内错过的触发，每个错过点仅补执行一次。

        选取条件：
          - 已启用
          - next_fire_at 在 24 小时窗口内（非太久以前的老旧触发）
          - next_fire_at <= now（已到时但尚未触发）
        fire() 执行后会将 next_fire_at 推进到未来，因此同一触发点不会被重复补执行。
        """
        now = datetime.now(dt_timezone.utc)
        threshold = now - timedelta(hours=self._MISFIRE_THRESHOLD_HOURS)

        stmt = select(Schedule).where(
            Schedule.enabled == True,  # noqa: E712
            Schedule.next_fire_at >= threshold,   # 仅补 24h 内的 misfire
            Schedule.next_fire_at <= now,          # 已过期但尚未触发
        )
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        count = 0
        for sch in schedules:
            try:
                await self.fire(db, sch.id)
                await db.commit()
                count += 1
            except Exception:
                pass

        return count

    async def advance_stale_schedules(self, db: AsyncSession) -> int:
        """
        推进陈旧调度的 next_fire_at 到未来触发点。

        当 next_fire_at 早于 24 小时窗口（即超过 24h 未触发）时：
        - 跳过补执行（避免一次性触发大量任务）
        - 仅推进 next_fire_at 到下一个未来触发点

        这样可避免 schedule 因长期未执行而"永久饿死"。
        """
        now = datetime.now(dt_timezone.utc)
        threshold = now - timedelta(hours=self._MISFIRE_THRESHOLD_HOURS)

        # 选取 next_fire_at 早于阈值的启用中调度
        stmt = select(Schedule).where(
            Schedule.enabled == True,  # noqa: E712
            Schedule.next_fire_at < threshold,  # 陈旧调度
        )
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        count = 0
        for sch in schedules:
            try:
                # 推进到下一个未来触发点
                sch.next_fire_at = self._calc_next_fire(sch.cron_expr, sch.timezone)
                await db.flush()
                count += 1
            except Exception:
                pass

        if count > 0:
            await db.commit()

        return count

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    def _validate_cron(self, cron_expr: str, timezone: str) -> bool:
        """验证 cron 表达式是否合法。"""
        try:
            croniter(cron_expr)
            return True
        except (ValueError, KeyError):
            return False

    def _calc_next_fire(self, cron_expr: str, tz_name: str) -> datetime:
        """计算下次触发时间（UTC，带时区信息）。"""
        import pytz
        try:
            tz = pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.timezone("Asia/Shanghai")

        now_local = datetime.now(tz)
        iter_ = croniter(cron_expr, now_local)
        next_local = iter_.get_next(datetime)
        # croniter 返回 naive datetime，附上时区后转 UTC
        if next_local.tzinfo is None:
            next_local = tz.localize(next_local)
        return next_local.astimezone(dt_timezone.utc)