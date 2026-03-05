"""
JSONP 回调剥离工具（PRD PUB-02 / PUB-06）。
百家号草稿响应格式：bjhdraft({...})
百家号发布响应格式：bjhpublish({...})
"""

import json
import re


def strip_jsonp(text: str) -> dict:
    """剥离 JSONP 回调包装，返回解析后的 dict。"""
    match = re.match(r"^\w+\((.+)\)$", text.strip(), re.DOTALL)
    if not match:
        raise ValueError(f"非 JSONP 格式响应: {text[:100]}")
    return json.loads(match.group(1))
