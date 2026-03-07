"""
封面搜索辅助工具。

目标：
  - 从标题 / 品类 / 主题 / 产品名生成更稳定的搜图关键词
  - 为不同品类提供更偏视觉化的兜底关键词，提升百家号图库命中率
"""

from __future__ import annotations

import re


_CATEGORY_COVER_FALLBACKS: dict[str, list[str]] = {
    "图书教育": ["读书", "书籍", "学习", "学生"],
    "家用日常": ["家居", "收纳", "清洁", "居家"],
    "精品服饰": ["穿搭", "服装", "时尚", "衣橱"],
    "食品生鲜": ["美食", "食材", "厨房", "餐桌"],
    "数码家电": ["数码", "家电", "设备", "科技"],
    "美妆个护": ["护肤", "美妆", "化妆品", "护理"],
    "母婴用品": ["母婴", "宝宝", "育儿", "儿童"],
    "运动户外": ["运动", "健身", "户外", "训练"],
    "鞋靴箱包": ["鞋子", "包包", "箱包", "搭配"],
    "汽车用品": ["汽车", "车品", "驾驶", "车内"],
    "珠宝配饰": ["珠宝", "饰品", "首饰", "配饰"],
    "宠物用品": ["宠物", "猫咪", "狗狗", "养宠"],
    "鲜花园艺": ["鲜花", "绿植", "园艺", "花园"],
    "零食干货": ["零食", "干货", "小吃", "零嘴"],
    "粮油调料": ["厨房", "调料", "食用油", "烹饪"],
    "医疗保健": ["健康", "保健", "体检", "医疗"],
    "家用器械": ["器械", "康复", "理疗", "家用医疗"],
    "中医养生": ["养生", "中医", "调理", "食疗"],
}

_TITLE_SPLIT_RE = re.compile(r"[，。！？：:；、“”‘’《》【】（）()、/\\|\-\s]+")
_CN_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


def build_cover_keywords(
    title: str,
    category: str,
    topic_keyword: str | None = None,
    product_name: str | None = None,
) -> list[str]:
    """
    生成封面搜索关键词优先级队列。

    顺序原则：
      1. 产品/主题词
      2. 标题核心短语
      3. 类目 + 主题组合
      4. 品类视觉化兜底词
    """
    candidates: list[str] = []

    def add(value: str | None) -> None:
        if not value:
            return
        normalized = _normalize_candidate(value)
        if not normalized:
            return
        if normalized not in candidates:
            candidates.append(normalized)

    add(product_name)
    add(topic_keyword)
    if product_name:
        add(f"{category}{product_name}")
    if topic_keyword:
        add(f"{category}{topic_keyword}")

    clean_title = _normalize_candidate(title)
    add(clean_title)

    for part in _TITLE_SPLIT_RE.split(title):
        normalized = _normalize_candidate(part)
        if 2 <= len(normalized) <= 12:
            add(normalized)

    for token in _CN_TOKEN_RE.findall(title):
        normalized = _normalize_candidate(token)
        if 2 <= len(normalized) <= 8:
            add(normalized)

    add(category)
    for fallback in _CATEGORY_COVER_FALLBACKS.get(category, []):
        add(fallback)

    return candidates


def _normalize_candidate(value: str) -> str:
    text = value.strip()
    if not text:
        return ""

    text = re.sub(r"[《》【】（）()\"'“”‘’]", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？：:；、,.!?\-_/\\|]+", "", text)
    return text[:16]
