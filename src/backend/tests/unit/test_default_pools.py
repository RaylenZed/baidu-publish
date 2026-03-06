from app.core.constants import CATEGORIES, PoolType
from app.core.default_pools import build_default_pool_rows


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
