from app.core.constants import CATEGORIES, PoolType
from app.core.default_pools import (
    build_default_pool_rows,
    build_starter_pool_rows_for_category,
)
from app.services.pool_service import merge_missing_pool_items


def test_default_pools_cover_all_categories_and_pool_types():
    rows = build_default_pool_rows()

    assert len(rows) == len(CATEGORIES) * 2 + 4

    angle_categories = {
        row["category"] for row in rows if row["pool_type"] == PoolType.ANGLE
    }
    persona_categories = {
        row["category"] for row in rows if row["pool_type"] == PoolType.PERSONA
    }

    assert angle_categories == set(CATEGORIES)
    assert persona_categories == set(CATEGORIES)

    universal_types = {
        row["pool_type"] for row in rows if row["category"] is None
    }
    assert universal_types == {
        PoolType.STYLE,
        PoolType.STRUCTURE,
        PoolType.TITLE_STYLE,
        PoolType.TIME_HOOK,
    }


def test_default_pool_items_are_enabled_and_weighted():
    rows = build_default_pool_rows()

    for row in rows:
        items = row["items"]
        assert items
        assert all(item["enabled"] is True for item in items)
        assert all(item["weight"] == 1 for item in items)
        assert all(isinstance(item["value"], str) and item["value"] for item in items)


def test_starter_pool_rows_for_new_category_only_create_category_specific_pools():
    rows = build_starter_pool_rows_for_category("办公家具")

    assert len(rows) == 2
    assert {row["pool_type"] for row in rows} == {PoolType.ANGLE, PoolType.PERSONA}
    assert all(row["category"] == "办公家具" for row in rows)
    assert all(row["items"] for row in rows)


def test_merge_missing_pool_items_appends_only_new_values():
    existing_items = [
        {"value": "书单推荐", "weight": 9, "enabled": False},
        {"value": "读后感", "weight": 3, "enabled": True},
    ]
    default_items = [
        {"value": "书单推荐", "weight": 1, "enabled": True},
        {"value": "经典重读", "weight": 1, "enabled": True},
    ]

    merged, added = merge_missing_pool_items(existing_items, default_items)

    assert added == 1
    assert merged[0] == existing_items[0]
    assert merged[1] == existing_items[1]
    assert merged[2] == default_items[1]
