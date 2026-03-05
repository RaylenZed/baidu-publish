"""
combo_id 格式化工具（PRD POOL-05）。
格式：A{角度序号}P{人设序号}S{风格序号}T{标题风格序号}
示例：A3P2S1T4
"""


def build_combo_id(angle: int, persona: int, style: int, title_style: int) -> str:
    return f"A{angle}P{persona}S{style}T{title_style}"


def parse_combo_id(combo_id: str) -> dict[str, int]:
    """解析 combo_id 为各维度序号字典。"""
    import re
    m = re.fullmatch(r"A(\d+)P(\d+)S(\d+)T(\d+)", combo_id)
    if not m:
        raise ValueError(f"combo_id 格式错误: {combo_id}")
    return {
        "angle": int(m.group(1)),
        "persona": int(m.group(2)),
        "style": int(m.group(3)),
        "title_style": int(m.group(4)),
    }
