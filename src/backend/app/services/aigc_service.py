"""
百度 AIGC 服务（PRD §AI-01~07 / PRD §5.3 AIGC 生成流程）

职责：
  - createDialogue → chat SSE → 解析 title/content
  - 生成初稿（generate_article）、润色（polish_article）
  - SSE 截断检测（PartialContentException → partial_content 风控）

通信细节（来源 v7 legacy 代码分析）：
  createDialogue  POST https://aigc.baidu.com/aigc/saas/pc/v1/aiNews/createDialogue
  chat            POST https://aigc.baidu.com/aigc/saas/pc/v1/aiNews/chat  (SSE)
  SSE 格式：每行 "data: {JSON}"，is_end=true 为终止标志。
  认证方式：与百家号共用同一 Cookie，无需额外 API Key。
"""

from __future__ import annotations

import json
import re

import httpx

from app.core.logging import get_logger
from app.schemas.pool import ComboResult

logger = get_logger(__name__)

_CREATE_URL = "https://aigc.baidu.com/aigc/saas/pc/v1/aiNews/createDialogue"
_CHAT_URL = "https://aigc.baidu.com/aigc/saas/pc/v1/aiNews/chat"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://aigc.baidu.com",
}

_MIN_PARTIAL_LENGTH = 500  # SSE 中断但内容 >= 此值时触发 partial_content 风控


class PartialContentException(Exception):
    """
    SSE 流中断，内容不完整但字数够用（>= 500 字）。
    触发 partial_content 风控：强制降级 draft_only，需人工确认后才可发布。
    """

    def __init__(self, title: str, body_md: str) -> None:
        super().__init__("SSE stream ended without is_end=True (partial_content)")
        self.title = title
        self.body_md = body_md


class AigcService:
    """百度 AIGC 对话与内容生成。"""

    # ── 公开方法 ──────────────────────────────────────────────────────────────

    async def generate_article(
        self,
        combo: ComboResult,
        category: str,
        topic_keyword: str | None,
        product_name: str | None,
        cookie: str,
        model: str,
        timeout: int,
    ) -> tuple[str, str]:
        """
        基于变量组合生成文章初稿（PRD §AI-02）。
        返回 (title, body_md)；SSE 截断时抛 PartialContentException。
        """
        prompt = self._build_generate_prompt(combo, category, topic_keyword, product_name)
        raw, is_partial = await self._call_aigc(prompt, cookie, model, timeout)
        title, body_md = self._parse_article(raw)
        if is_partial:
            raise PartialContentException(title, body_md)
        return title, body_md

    async def polish_article(
        self,
        raw_article: str,
        category: str,
        cookie: str,
        model: str,
        timeout: int,
    ) -> tuple[str, str]:
        """
        对初稿进行润色（PRD §AI-03）。
        返回 (title, body_md)；SSE 截断时抛 PartialContentException。
        """
        prompt = self._build_polish_prompt(raw_article, category)
        raw, is_partial = await self._call_aigc(prompt, cookie, model, timeout)
        title, body_md = self._parse_article(raw)
        if is_partial:
            raise PartialContentException(title, body_md)
        return title, body_md

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    async def _call_aigc(
        self, prompt: str, cookie: str, model: str, timeout: int
    ) -> tuple[str, bool]:
        """
        createDialogue → chat SSE。
        返回 (raw_text, is_partial)。
        is_partial=True 表示 SSE 未收到 is_end=True 但内容 >= 500 字。
        """
        cookies = _parse_cookies(cookie)
        http_timeout = httpx.Timeout(
            connect=10.0, read=float(timeout), write=10.0, pool=10.0
        )
        async with httpx.AsyncClient(
            cookies=cookies,
            headers=_DEFAULT_HEADERS,
            timeout=http_timeout,
        ) as client:
            # Step 1: createDialogue
            resp = await client.post(
                _CREATE_URL,
                headers={"Referer": "https://aigc.baidu.com/aiArticle"},
                json={},
            )
            resp.raise_for_status()
            dialogue_id = resp.json().get("data", {}).get("dialogue_id", "")
            if not dialogue_id:
                raise RuntimeError(f"createDialogue 失败: {resp.text[:200]}")

            # Step 2: chat SSE
            last_data: dict | None = None
            stream_ended = False
            async with client.stream(
                "POST",
                _CHAT_URL,
                headers={
                    "Accept": "text/event-stream",
                    "Referer": f"https://aigc.baidu.com/chat/{dialogue_id}",
                },
                json={
                    "query": prompt,
                    "enter_point": 1,
                    "model": model,
                    "dialogue_id": dialogue_id,
                    "chat_type": 8,
                },
            ) as stream:
                async for line in stream.aiter_lines():
                    if not line.strip():
                        continue
                    raw = line.strip()
                    if raw.startswith("data:"):
                        raw = raw[5:].strip()
                    try:
                        parsed = json.loads(raw)
                        last_data = parsed
                        if parsed.get("data", {}).get("is_end") is True:
                            stream_ended = True
                            break
                    except json.JSONDecodeError:
                        continue

        if last_data is None:
            raise RuntimeError("AIGC 未返回任何内容")

        content_obj = last_data.get("data", {}).get("content", {})
        title = content_obj.get("title", "")
        content = content_obj.get("content", "")

        # HTML → Markdown（AIGC 有时返回 HTML 片段）
        if content and ("<p>" in content or "<h" in content):
            content = _html_to_md(content)

        raw_text = f"标题：{title}\n\n{content}" if title else content

        if not stream_ended:
            # SSE 未正常结束
            if len(content) >= _MIN_PARTIAL_LENGTH:
                return raw_text, True  # partial_content 风控触发
            raise RuntimeError(
                f"AIGC 流异常中断，仅收到 {len(content)} 字（< {_MIN_PARTIAL_LENGTH} 字），内容不可用"
            )

        if not content:
            raise RuntimeError("AIGC 返回内容为空")

        return raw_text, False

    @staticmethod
    def _build_generate_prompt(
        combo: ComboResult,
        category: str,
        topic_keyword: str | None,
        product_name: str | None,
    ) -> str:
        """拼装生成 Prompt（sys_prompt + user_prompt）。"""
        extra = ""
        if topic_keyword:
            extra += f"\n- 主题关键词：{topic_keyword}"
        if product_name:
            extra += f"\n- 重点产品：{product_name}"

        extra_section = f"\n\n## 额外要求{extra}" if extra else ""

        sys_prompt = f"""# 最高优先级指令
你正在为百家号【{category}】品类账号写文章。
文章内容必须100%围绕【{category}】展开，这是不可违反的硬性要求。

## 品类约束（极其重要，违反则文章作废）
- 文章的主题、场景、产品/品牌/知识点，都必须属于【{category}】领域
- 文章中必须至少出现3个与【{category}】直接相关的具体产品名、品牌名或专业术语
- 禁止跑题！不要写成个人成长、时间管理、心灵鸡汤等与品类无关的内容
- 不要写成广告文或推销文，这是纯内容分享

## 你的身份设定
你是一个{combo.persona}，用自己的真实经历和感受来写这篇关于【{category}】的文章。

## 本次创作参数
- 内容品类：{category}
- 切入角度：{combo.angle}
- 写作风格：{combo.style}
- 文章结构：{combo.structure}
- 标题风格：{combo.title_style}
- 时间/场景背景：{combo.time_hook}

## 写作要求（10条具体规则）
1. 字数800-1200字
2. 纯内容文章，绝对不带任何商品推广、购买链接、价格信息、店铺名
3. 必须包含具体的、真实存在的产品名/品牌名（且必须是{category}领域的）
4. 像真人分享，有个人经历、具体场景、真实情感
5. 不要出现开头套话（如：今天给大家分享、废话不多说等）
6. 可以有口语化表达、省略号、感叹词
7. 开头3秒抓住读者
8. 标题15-30字，有吸引力但不标题党
9. 适当加粗1-2个重点句子
10. 结尾引发互动（提问、征集经验等）{extra_section}

## 输出格式
标题：xxx

正文内容..."""

        user_prompt = f"""请以"{combo.persona}"的身份，围绕【{category}】品类，从"{combo.angle}"的角度，用"{combo.style}"的风格，写一篇百家号文章。

记住：
- 品类是【{category}】，所有内容必须与此相关
- 你的人设是{combo.persona}
- 文章结构用{combo.structure}
- 标题风格用{combo.title_style}
- 融入"{combo.time_hook}"的时间/场景背景
- 必须出现至少3个{category}领域的真实品牌名或产品名

现在开始写："""

        return f"{sys_prompt}\n\n---\n{user_prompt}"

    @staticmethod
    def _build_polish_prompt(raw_article: str, category: str) -> str:
        """拼装润色 Prompt。"""
        polish_sys = f"""你是文章润色专家。当前品类：【{category}】

## 品类一致性检查（最高优先级）
先检查文章是否围绕【{category}】品类展开。如果文章与该品类严重不符，
你必须完全重写一篇围绕【{category}】的文章，而不是只做润色。

## 润色原则
1. 去除AI痕迹：删掉机械化过渡词（首先/其次/最后）、排比句、空话
2. 增加真人感：加入口语化表达（说真的、emmm、哈哈、真的绝了），段落长短有变化
3. 保留核心内容：产品名/品牌名保留，不要删掉具体细节
4. 百家号适配：标题15-30字，正文800-1200字，结尾互动，加粗1-2个金句
5. 不要加任何商品链接、价格、店铺名等推广内容
6. 确保文章中至少有3个{category}领域的真实品牌名/产品名

## 输出格式
标题：xxx

正文内容..."""
        return f"{polish_sys}\n\n---\n请润色以下文章，去除AI味，增加真人感：\n\n{raw_article}"

    @staticmethod
    def _parse_article(text: str) -> tuple[str, str]:
        """从 AIGC 输出中解析标题和正文，返回 (title, body_md)。"""
        lines = text.strip().split("\n")
        title = ""
        body_start = 0

        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("标题：") or s.startswith("标题:"):
                title = s.replace("标题：", "").replace("标题:", "").strip()
                body_start = i + 1
                break
            elif s.startswith("# ") and i == 0:
                title = s[2:].strip()
                body_start = 1
                break

        if not title:
            title = lines[0].strip()[:30]
            body_start = 1

        body = "\n".join(lines[body_start:]).strip()
        return title, body


# ── 模块级工具函数 ────────────────────────────────────────────────────────────

def _parse_cookies(cookie_str: str) -> dict[str, str]:
    """将 Cookie 字符串解析为 httpx 可用的字典。"""
    cookies: dict[str, str] = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def _html_to_md(html: str) -> str:
    """简易 HTML → Markdown 转换（处理 AIGC 返回的 HTML 片段）。"""
    text = re.sub(r"<h[1-3][^>]*>(.*?)</h[1-3]>", r"## \1", html, flags=re.DOTALL)
    text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
