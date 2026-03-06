"""add categories table

Revision ID: 0002_add_categories_table
Revises: 0001_initial_schema
Create Date: 2026-03-06 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_add_categories_table"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("name", sa.String(length=20), nullable=False, comment="品类名称，全局唯一，长度 1-20"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"), comment="是否启用"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="排序值，越小越靠前"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "ix_categories_enabled_sort_order",
        "categories",
        ["enabled", "sort_order"],
        unique=False,
    )

    categories = sa.table(
        "categories",
        sa.column("name", sa.String(length=20)),
        sa.column("enabled", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        categories,
        [
            {"name": "图书教育", "enabled": True, "sort_order": 1},
            {"name": "家用日常", "enabled": True, "sort_order": 2},
            {"name": "精品服饰", "enabled": True, "sort_order": 3},
            {"name": "食品生鲜", "enabled": True, "sort_order": 4},
            {"name": "数码家电", "enabled": True, "sort_order": 5},
            {"name": "美妆个护", "enabled": True, "sort_order": 6},
            {"name": "母婴用品", "enabled": True, "sort_order": 7},
            {"name": "运动户外", "enabled": True, "sort_order": 8},
            {"name": "鞋靴箱包", "enabled": True, "sort_order": 9},
            {"name": "汽车用品", "enabled": True, "sort_order": 10},
            {"name": "珠宝配饰", "enabled": True, "sort_order": 11},
            {"name": "宠物用品", "enabled": True, "sort_order": 12},
            {"name": "鲜花园艺", "enabled": True, "sort_order": 13},
            {"name": "零食干货", "enabled": True, "sort_order": 14},
            {"name": "粮油调料", "enabled": True, "sort_order": 15},
            {"name": "医疗保健", "enabled": True, "sort_order": 16},
            {"name": "家用器械", "enabled": True, "sort_order": 17},
            {"name": "中医养生", "enabled": True, "sort_order": 18},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_categories_enabled_sort_order", table_name="categories")
    op.drop_table("categories")
