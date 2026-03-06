"""
内置默认品类种子。

数据来源：
  - PRD 约定的 18 个基础品类

用途：
  - 数据库初始化时补齐 categories 表
  - 保持旧版硬编码品类向数据库真源的平滑迁移
"""

from __future__ import annotations

from app.core.constants import CATEGORIES


def build_default_categories() -> list[dict[str, object]]:
    """返回默认品类种子列表，按 PRD 原始顺序分配 sort_order。"""
    return [
        {
            "name": name,
            "enabled": True,
            "sort_order": index,
        }
        for index, name in enumerate(CATEGORIES, start=1)
    ]
