"""
品类主数据服务。

职责：
  - categories 表 CRUD
  - 运行时校验品类是否合法/是否启用
  - 新增品类时自动补齐 starter 变量池
  - 重命名品类时同步更新历史业务数据中的品类字符串
"""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.default_categories import build_default_categories
from app.core.exceptions import NotFoundException, ValidationException
from app.models.account import Account
from app.models.audit import ContentEvent
from app.models.category import Category
from app.models.pool import ComboHistory, VariablePool
from app.models.task import Task
from app.schemas.category import CreateCategoryRequest, UpdateCategoryRequest


class CategoryService:
    """系统品类管理。"""

    async def list_category_names(
        self,
        db: AsyncSession,
        *,
        enabled_only: bool = True,
    ) -> list[str]:
        stmt = select(Category.name)
        if enabled_only:
            stmt = stmt.where(Category.enabled.is_(True))
        stmt = stmt.order_by(Category.sort_order.asc(), Category.id.asc())
        rows = await db.execute(stmt)
        return [row[0] for row in rows.all()]

    async def list_categories(self, db: AsyncSession) -> list[Category]:
        result = await db.execute(
            select(Category).order_by(Category.sort_order.asc(), Category.id.asc())
        )
        return list(result.scalars().all())

    async def get_category(self, db: AsyncSession, category_id: int) -> Category:
        row = await db.get(Category, category_id)
        if row is None:
            raise NotFoundException(f"品类 {category_id} 不存在")
        return row

    async def seed_default_categories(self, db: AsyncSession) -> int:
        """
        补齐默认品类，不覆盖已存在记录。
        返回本次新增数量。
        """
        defaults = build_default_categories()
        rows = await db.execute(select(Category.name))
        existing_names = {name for name, in rows.all()}

        created = 0
        for item in defaults:
            if item["name"] in existing_names:
                continue
            db.add(Category(**item))
            existing_names.add(str(item["name"]))
            created += 1

        await db.flush()
        return created

    async def ensure_category_exists(
        self,
        db: AsyncSession,
        category_name: str,
        *,
        enabled_only: bool = False,
    ) -> str:
        normalized = category_name.strip()
        if not normalized:
            raise ValidationException("品类不能为空")

        stmt = select(Category.name).where(Category.name == normalized)
        if enabled_only:
            stmt = stmt.where(Category.enabled.is_(True))

        row = await db.scalar(stmt)
        if row is None:
            if enabled_only:
                raise ValidationException(f"品类「{normalized}」不在启用品类列表中")
            raise ValidationException(f"品类「{normalized}」不在系统品类列表中")
        return normalized

    async def validate_category_names(
        self,
        db: AsyncSession,
        category_names: list[str],
        *,
        min_count: int,
        max_count: int,
        enabled_only: bool = True,
    ) -> list[str]:
        normalized = [name.strip() for name in category_names if name and name.strip()]
        if not (min_count <= len(normalized) <= max_count):
            raise ValidationException(f"品类数量必须在 {min_count}-{max_count} 个之间")
        if len(set(normalized)) != len(normalized):
            raise ValidationException("品类不能重复")

        stmt = select(Category.name).where(Category.name.in_(normalized))
        if enabled_only:
            stmt = stmt.where(Category.enabled.is_(True))
        rows = await db.execute(stmt)
        valid_names = {row[0] for row in rows.all()}

        invalid = [name for name in normalized if name not in valid_names]
        if invalid:
            scope = "启用" if enabled_only else "系统"
            raise ValidationException(f"品类 {invalid} 不在{scope}品类列表中")
        return normalized

    async def create_category(
        self,
        db: AsyncSession,
        data: CreateCategoryRequest,
    ) -> Category:
        name = data.name.strip()
        await self._ensure_name_available(db, name)

        row = Category(
            name=name,
            enabled=data.enabled,
            sort_order=data.sort_order if data.sort_order is not None else await self._next_sort_order(db),
        )
        db.add(row)
        await db.flush()

        # 新品类创建后自动生成 angle/persona starter 变量池，避免后续任务抽样时报缺池。
        from app.services.pool_service import PoolService

        await PoolService().ensure_category_pools(db, name)
        await db.refresh(row)
        return row

    async def update_category(
        self,
        db: AsyncSession,
        category_id: int,
        data: UpdateCategoryRequest,
    ) -> Category:
        row = await self.get_category(db, category_id)
        old_name = row.name

        if data.name is not None and data.name != row.name:
            await self._ensure_name_available(db, data.name, exclude_id=category_id)
            row.name = data.name
        if data.enabled is not None:
            row.enabled = data.enabled
        if data.sort_order is not None:
            row.sort_order = data.sort_order

        if row.name != old_name:
            await self._rename_category_references(db, old_name, row.name)

        await db.flush()
        await db.refresh(row)
        return row

    async def delete_category(self, db: AsyncSession, category_id: int) -> None:
        row = await self.get_category(db, category_id)
        usage = await self._count_runtime_usage(db, row.name)
        if usage > 0:
            raise ValidationException(
                f"品类「{row.name}」仍被账号或历史任务引用，不能删除。建议改为停用。"
            )

        await db.execute(delete(VariablePool).where(VariablePool.category == row.name))
        await db.delete(row)
        await db.flush()

    async def _ensure_name_available(
        self,
        db: AsyncSession,
        name: str,
        *,
        exclude_id: int | None = None,
    ) -> None:
        stmt = select(Category.id).where(Category.name == name)
        if exclude_id is not None:
            stmt = stmt.where(Category.id != exclude_id)
        existing = await db.scalar(stmt)
        if existing is not None:
            raise ValidationException(f"品类「{name}」已存在")

    async def _next_sort_order(self, db: AsyncSession) -> int:
        current_max = await db.scalar(select(func.max(Category.sort_order)))
        return int(current_max or 0) + 1

    async def _rename_category_references(
        self,
        db: AsyncSession,
        old_name: str,
        new_name: str,
    ) -> None:
        accounts = (
            await db.execute(
                select(Account).where(Account.categories.contains([old_name]))
            )
        ).scalars().all()
        for account in accounts:
            account.categories = [
                new_name if name == old_name else name
                for name in (account.categories or [])
            ]

        await db.execute(
            update(Task).where(Task.category == old_name).values(category=new_name)
        )
        await db.execute(
            update(VariablePool).where(VariablePool.category == old_name).values(category=new_name)
        )
        await db.execute(
            update(ComboHistory).where(ComboHistory.category == old_name).values(category=new_name)
        )
        await db.execute(
            update(ContentEvent).where(ContentEvent.category == old_name).values(category=new_name)
        )

    async def _count_runtime_usage(self, db: AsyncSession, category_name: str) -> int:
        account_count = 0
        accounts = (
            await db.execute(
                select(Account.id).where(Account.categories.contains([category_name]))
            )
        ).all()
        account_count = len(accounts)

        task_count = await db.scalar(
            select(func.count()).select_from(Task).where(Task.category == category_name)
        ) or 0
        combo_count = await db.scalar(
            select(func.count()).select_from(ComboHistory).where(ComboHistory.category == category_name)
        ) or 0
        event_count = await db.scalar(
            select(func.count()).select_from(ContentEvent).where(ContentEvent.category == category_name)
        ) or 0

        return int(account_count + task_count + combo_count + event_count)
