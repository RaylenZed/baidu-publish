"""
变量池服务（PRD §POOL-01~06 / PRD §6.5 变量池）

职责：
  - 6 维变量池 CRUD
  - 加权随机抽取（angle/persona 为品类专属，其余 4 个通用）
  - combo_id 生成（格式 A{n}P{n}S{n}T{n}）
  - 7 天去重（软规则，最多重试 3 次后放行）
  - 组合历史记录
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PoolType
from app.core.default_pools import (
    build_default_pool_rows,
    build_starter_pool_rows_for_category,
)
from app.core.exceptions import NotFoundException, ValidationException
from app.models.pool import ComboHistory, VariablePool
from app.schemas.pool import ComboResult, PoolItem, SeedPoolsResponse, UpdatePoolRequest
from app.utils.combo import build_combo_id

# 品类专属池类型（需要提供 category）
CATEGORY_POOL_TYPES: frozenset[PoolType] = frozenset({PoolType.ANGLE, PoolType.PERSONA})
# 通用池类型（category 为 NULL）
UNIVERSAL_POOL_TYPES: frozenset[PoolType] = frozenset({
    PoolType.STYLE, PoolType.STRUCTURE, PoolType.TITLE_STYLE, PoolType.TIME_HOOK
})

_DEDUP_MAX_RETRIES = 3
_DEDUP_DAYS = 7


def _weighted_choice(items: list[dict]) -> tuple[str, int]:
    """
    从 items 中按 weight 加权随机选一个 enabled 条目。
    返回 (value, 1-based-index-in-original-items)。
    """
    enabled = [(i, item) for i, item in enumerate(items) if item.get("enabled", True)]
    if not enabled:
        raise ValidationException("池中没有可用的条目（enabled=false），请至少启用一个条目")

    weights = [item.get("weight", 1) for _, item in enabled]
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0.0
    for orig_idx, item in enabled:
        cumulative += item.get("weight", 1)
        if r <= cumulative:
            return item["value"], orig_idx + 1  # 1-based

    # 浮点边界兜底
    last_idx, last_item = enabled[-1]
    return last_item["value"], last_idx + 1


def merge_missing_pool_items(
    existing_items: list[dict],
    default_items: list[dict],
) -> tuple[list[dict], int]:
    """
    将 default_items 中缺失的 value 追加到 existing_items 末尾。

    约束：
      - 仅按 value 判重
      - 不改动已有条目的 weight / enabled / 顺序
      - 缺失默认条目使用默认 weight/enabled
    """
    existing_values = {
        str(item.get("value")).strip()
        for item in existing_items
        if isinstance(item, dict) and item.get("value")
    }
    missing_items = [
        item for item in default_items
        if str(item.get("value")).strip() not in existing_values
    ]
    if not missing_items:
        return list(existing_items), 0
    return [*existing_items, *missing_items], len(missing_items)


class PoolService:
    """变量池加权随机与组合管理。"""

    # ── 查询 ─────────────────────────────────────────────────────────────────

    async def list_pools(self, db: AsyncSession) -> list[VariablePool]:
        """返回全部变量池（按 pool_type, category 排序）。"""
        result = await db.execute(
            select(VariablePool).order_by(VariablePool.pool_type, VariablePool.category)
        )
        return list(result.scalars().all())

    async def get_pool(
        self,
        db: AsyncSession,
        pool_type: PoolType,
        category: str | None,
    ) -> VariablePool:
        """获取指定池，不存在时抛 NotFoundException。"""
        row = await db.scalar(
            select(VariablePool).where(
                and_(
                    VariablePool.pool_type == pool_type,
                    VariablePool.category == category,
                )
            )
        )
        if row is None:
            cat_desc = f"/{category}" if category else ""
            raise NotFoundException(f"变量池 {pool_type.value}{cat_desc} 不存在，请先通过 PUT 创建")
        return row

    async def seed_default_pools(self, db: AsyncSession) -> SeedPoolsResponse:
        """
        补齐内置默认变量池。

        行为：
          - 缺失池：直接创建
          - 已存在池：补齐缺失的默认条目
          - 已有条目：保持原顺序、权重、启用状态不变
        """
        defaults = build_default_pool_rows()
        result = await db.execute(
            select(VariablePool)
        )
        existing = {
            (row.pool_type, row.category): row
            for row in result.scalars().all()
        }

        created = 0
        merged_pools = 0
        merged_items = 0
        skipped = 0
        for row in defaults:
            key = (row["pool_type"], row["category"])
            existing_row = existing.get(key)
            if existing_row is None:
                new_row = VariablePool(**row)
                db.add(new_row)
                existing[key] = new_row
                created += 1
                continue

            merged, added = merge_missing_pool_items(
                existing_row.items or [],
                row["items"],
            )
            if added > 0:
                existing_row.items = merged
                merged_pools += 1
                merged_items += added
            else:
                skipped += 1

        await db.flush()
        total_defaults = len(defaults)
        return SeedPoolsResponse(
            created=created,
            merged_pools=merged_pools,
            merged_items=merged_items,
            skipped=skipped,
            total_defaults=total_defaults,
        )

    async def ensure_category_pools(self, db: AsyncSession, category: str) -> int:
        """
        为新品类补齐 angle/persona starter 池。
        返回本次新增池数量（0-2）。
        """
        starter_rows = build_starter_pool_rows_for_category(category)
        result = await db.execute(
            select(VariablePool.pool_type, VariablePool.category).where(
                and_(
                    VariablePool.pool_type.in_(CATEGORY_POOL_TYPES),
                    VariablePool.category == category,
                )
            )
        )
        existing = {(pool_type, pool_category) for pool_type, pool_category in result.all()}

        created = 0
        for row in starter_rows:
            key = (row["pool_type"], row["category"])
            if key in existing:
                continue
            db.add(VariablePool(**row))
            created += 1

        await db.flush()
        return created

    # ── 更新 / 创建（upsert）─────────────────────────────────────────────────

    async def update_pool(
        self,
        db: AsyncSession,
        pool_type: PoolType,
        data: UpdatePoolRequest,
    ) -> VariablePool:
        """
        更新（或首次创建）变量池。
        - 品类专属池（angle/persona）：data.category 必填且须在系统品类表中
        - 通用池：忽略 data.category（强制 NULL）
        """
        # 决定实际存储的 category
        if pool_type in CATEGORY_POOL_TYPES:
            if not data.category:
                raise ValidationException(
                    f"{pool_type.value} 是品类专属池，更新时必须提供 category"
                )
            from app.services.category_service import CategoryService

            actual_category = await CategoryService().ensure_category_exists(
                db,
                data.category,
                enabled_only=False,
            )
        else:
            actual_category = None  # 通用池不绑定品类

        items_raw = [item.model_dump() for item in data.items]

        row = await db.scalar(
            select(VariablePool).where(
                and_(
                    VariablePool.pool_type == pool_type,
                    VariablePool.category == actual_category,
                )
            )
        )
        if row is None:
            row = VariablePool(
                pool_type=pool_type,
                category=actual_category,
                items=items_raw,
            )
            db.add(row)
        else:
            row.items = items_raw

        await db.flush()
        await db.refresh(row)
        return row

    # ── 抽样（sample_combo） ──────────────────────────────────────────────────

    async def sample_combo(
        self,
        db: AsyncSession,
        account_id: int,
        category: str,
    ) -> ComboResult:
        """
        从 6 维池中加权随机抽取一套变量组合（PRD POOL-04/05）。

        算法：
          1. 加载 6 个池（angle/persona 按品类，其余通用）
          2. 每维加权随机抽一个 enabled 条目
          3. 构建 combo_id（A/P/S/T 四维序号）
          4. 查询近 7 天历史，若重复则重抽（最多 3 次，超限直接放行）
          5. 返回 ComboResult（不写 combo_history，由 TaskService 负责）
        """
        pools = await self._load_all_pools(db, category)

        best: ComboResult | None = None
        for _ in range(_DEDUP_MAX_RETRIES):
            combo = self._sample_once(pools)
            if best is None:
                best = combo
            # 检查 7 天去重
            is_dup = await self._is_duplicate(db, account_id, category, combo.combo_id)
            if not is_dup:
                return combo
            best = combo  # 记录最新一次结果（如全部重复，返回最后一次）

        # 超过重试次数，放行（软规则）
        return best  # type: ignore[return-value]

    async def record_combo(
        self,
        db: AsyncSession,
        account_id: int,
        category: str,
        combo_id: str,
        task_id: int | None = None,
    ) -> None:
        """将已使用的 combo 写入历史（由 TaskService 在任务创建后调用）。"""
        db.add(ComboHistory(
            account_id=account_id,
            category=category,
            combo_id=combo_id,
            task_id=task_id,
        ))
        await db.flush()

    # ── 历史查询 ──────────────────────────────────────────────────────────────

    async def get_combo_history(
        self,
        db: AsyncSession,
        account_id: int | None,
        category: str | None,
        days: int = 7,
    ) -> list[ComboHistory]:
        """返回近 N 天内的组合使用历史，可按账号/品类过滤。"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        conditions = [ComboHistory.used_at >= since]
        if account_id is not None:
            conditions.append(ComboHistory.account_id == account_id)
        if category is not None:
            conditions.append(ComboHistory.category == category)

        result = await db.execute(
            select(ComboHistory)
            .where(and_(*conditions))
            .order_by(ComboHistory.used_at.desc())
        )
        return list(result.scalars().all())

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    async def _load_all_pools(
        self, db: AsyncSession, category: str
    ) -> dict[PoolType, list[dict]]:
        """加载 6 个池的 items 数据，通用池 category=NULL，专属池 category=给定值。"""
        result = await db.execute(
            select(VariablePool).where(
                (
                    (VariablePool.pool_type.in_(UNIVERSAL_POOL_TYPES))
                    & (VariablePool.category.is_(None))
                ) | (
                    (VariablePool.pool_type.in_(CATEGORY_POOL_TYPES))
                    & (VariablePool.category == category)
                )
            )
        )
        rows = {row.pool_type: row.items for row in result.scalars().all()}

        # 校验 6 个池均已配置
        missing = []
        for pt in PoolType:
            if pt not in rows:
                missing.append(pt.value)
        if missing:
            raise ValidationException(
                f"变量池未配置完整，缺少：{', '.join(missing)}。请先通过 PUT /pools/{{pool_type}} 完善配置"
            )
        return rows

    def _sample_once(self, pools: dict[PoolType, list[dict]]) -> ComboResult:
        """执行一次 6 维抽样，构建 ComboResult。"""
        angle_val, angle_idx = _weighted_choice(pools[PoolType.ANGLE])
        persona_val, persona_idx = _weighted_choice(pools[PoolType.PERSONA])
        style_val, style_idx = _weighted_choice(pools[PoolType.STYLE])
        structure_val, _ = _weighted_choice(pools[PoolType.STRUCTURE])
        title_style_val, title_style_idx = _weighted_choice(pools[PoolType.TITLE_STYLE])
        time_hook_val, _ = _weighted_choice(pools[PoolType.TIME_HOOK])

        combo_id = build_combo_id(angle_idx, persona_idx, style_idx, title_style_idx)
        return ComboResult(
            combo_id=combo_id,
            angle=angle_val,
            persona=persona_val,
            style=style_val,
            structure=structure_val,
            title_style=title_style_val,
            time_hook=time_hook_val,
            angle_idx=angle_idx,
            persona_idx=persona_idx,
            style_idx=style_idx,
            title_style_idx=title_style_idx,
        )

    async def _is_duplicate(
        self,
        db: AsyncSession,
        account_id: int,
        category: str,
        combo_id: str,
    ) -> bool:
        """检查近 7 天内是否已使用过该 combo_id（同账号同品类）。"""
        since = datetime.now(timezone.utc) - timedelta(days=_DEDUP_DAYS)
        count = await db.scalar(
            select(func.count()).select_from(ComboHistory).where(
                and_(
                    ComboHistory.account_id == account_id,
                    ComboHistory.category == category,
                    ComboHistory.combo_id == combo_id,
                    ComboHistory.used_at >= since,
                )
            )
        )
        return bool(count and count > 0)
