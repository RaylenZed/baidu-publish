"""
百家号 API 封装（PRD §PUB-01~06 / PRD §5.4 发布流程）

职责：
  - Cookie 有效性检测（从编辑页提取 JWT edit_token）
  - 草稿保存（save_draft）
  - 封面图搜索与自动裁剪（search_cover）
  - 文章发布（publish_article）
  - Markdown → 百家号兼容 HTML（md_to_html）

API 来源：v7 legacy 代码（bjh_auto_full_v7.py）分析迁移。
认证方式：Cookie + edit_token（从编辑页 HTML 提取的 JWT）。
"""

from __future__ import annotations

import json
import re

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_BJH_BASE = "https://baijiahao.baidu.com"
_EDIT_PAGE_URL = f"{_BJH_BASE}/builder/rc/edit"
_SAVE_DRAFT_URL = f"{_BJH_BASE}/pcui/article/save"
_PIC_SEARCH_URL = f"{_BJH_BASE}/aigc/bjh/pc/v1/picSearch"
_AUTO_CROP_URL = f"{_BJH_BASE}/materialui/picture/auto_cutting"
_PUBLISH_URL = f"{_BJH_BASE}/pcui/article/publish"

_COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 编辑页 JWT 提取 Regex
_TOKEN_RE = re.compile(r'window\.__BJH__INIT__AUTH__\s*=\s*["\']([^"\']+)["\']')


class BjhService:
    """百家号 HTTP API 封装。"""

    # ── 公开方法 ──────────────────────────────────────────────────────────────

    async def get_edit_token(self, cookie: str, timeout: float = 15.0) -> str:
        """
        从百家号编辑页面 HTML 提取 JWT Token（PRD §PUB-01）。
        Token 用于后续草稿/封面/发布请求的 Token 请求头。
        抛 RuntimeError 若 cookie 失效或无法提取 token。
        """
        cookies = _parse_cookies(cookie)
        async with httpx.AsyncClient(
            cookies=cookies,
            headers=_COMMON_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            resp = await client.get(_EDIT_PAGE_URL)
            resp.raise_for_status()
            match = _TOKEN_RE.search(resp.text)
            if not match:
                raise RuntimeError("编辑页 JWT 提取失败，Cookie 可能已过期")
            return match.group(1)

    async def save_draft(
        self,
        cookie: str,
        edit_token: str,
        title: str,
        body_html: str,
        timeout: float = 60.0,
    ) -> str:
        """
        保存草稿，返回 bjh_article_id（PRD §PUB-02）。
        抛 RuntimeError 若保存失败。
        """
        cookies = _parse_cookies(cookie)
        async with httpx.AsyncClient(
            cookies=cookies,
            headers=_COMMON_HEADERS,
            timeout=timeout,
        ) as client:
            resp = await client.post(
                _SAVE_DRAFT_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": _BJH_BASE,
                    "Referer": _EDIT_PAGE_URL,
                    "Token": edit_token,
                },
                params={"callback": "bjhdraft"},
                data={"title": title, "content": body_html, "type": "news"},
            )
            resp.raise_for_status()

            text = resp.text
            if text.startswith("bjhdraft("):
                text = text[9:-1]
            data = json.loads(text)
            if data.get("errno") != 0:
                raise RuntimeError(f"草稿保存失败: {data.get('errmsg', 'unknown')}")

            article_id = str(data.get("ret", {}).get("article_id", ""))
            if not article_id:
                raise RuntimeError("草稿保存成功但未返回 article_id")
            return article_id

    async def search_cover(
        self,
        cookie: str,
        edit_token: str,
        keyword: str,
        bjh_article_id: str,
        timeout: float = 60.0,
    ) -> str | None:
        """
        搜索正版图库并自动裁剪，返回封面 URL 或 None（PRD §PUB-03）。
        失败时静默返回 None（不阻断发布流程，PRD 明确封面图可为空）。
        """
        try:
            cookies = _parse_cookies(cookie)
            referer = f"{_EDIT_PAGE_URL}?type=news&article_id={bjh_article_id}"
            async with httpx.AsyncClient(
                cookies=cookies,
                headers=_COMMON_HEADERS,
                timeout=timeout,
            ) as client:
                # 搜索图片
                resp = await client.post(
                    _PIC_SEARCH_URL,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Origin": _BJH_BASE,
                        "Referer": referer,
                        "Token": edit_token,
                    },
                    data={"page_no": "0", "keyword": keyword, "page_size": "5"},
                )
                imglist = resp.json().get("data", {}).get("imglist", [])
                if not imglist:
                    return None

                raw_url = imglist[0].get("bjh_watermark_url") or imglist[0].get("detail_url", "")
                if not raw_url:
                    return None

                # 自动裁剪为封面比例
                resp2 = await client.post(
                    _AUTO_CROP_URL,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Origin": _BJH_BASE,
                        "Referer": referer,
                        "Token": edit_token,
                    },
                    data={
                        "org_url": raw_url,
                        "type": "news",
                        "cutting_type": "cover_image",
                    },
                )
                new_url = resp2.json().get("data", {}).get("new_url", "")
                return new_url or raw_url

        except Exception as exc:
            logger.warning(
                "封面图获取失败（跳过）",
                extra={"keyword": keyword, "error": str(exc)},
            )
            return None

    async def search_cover_candidates(
        self,
        cookie: str,
        edit_token: str,
        keywords: list[str],
        bjh_article_id: str,
        timeout: float = 60.0,
    ) -> tuple[str | None, str | None, list[str]]:
        """
        按候选关键词依次搜索封面。

        返回：
          (cover_url, matched_keyword, attempted_keywords)
        """
        attempted: list[str] = []
        for keyword in keywords:
            normalized = keyword.strip()
            if not normalized or normalized in attempted:
                continue
            attempted.append(normalized)
            cover_url = await self.search_cover(
                cookie,
                edit_token,
                normalized,
                bjh_article_id,
                timeout=timeout,
            )
            if cover_url:
                return cover_url, normalized, attempted

        return None, None, attempted

    async def publish_article(
        self,
        cookie: str,
        edit_token: str,
        bjh_article_id: str,
        title: str,
        body_html: str,
        cover_url: str,
        cate_d1: str,
        cate_d2: str,
        timeout: float = 60.0,
    ) -> dict:
        """
        正式发布文章（PRD §PUB-05）。
        返回原始响应字典（errno=0 为成功）。
        """
        if cover_url:
            cover_images_json = json.dumps([{
                "src": cover_url,
                "cropData": {},
                "machine_chooseimg": 0,
                "isLegal": 0,
                "cover_source_tag": "text",
            }])
            cover_map_json = json.dumps([{"src": cover_url, "origin_src": cover_url}])
        else:
            cover_images_json = json.dumps([])
            cover_map_json = json.dumps([])

        plain = re.sub(r"<[^>]+>", "", body_html)
        abstract = plain[:120]

        form_data: dict[str, str] = {
            "type": "news",
            "title": title,
            "content": body_html,
            "abstract": abstract,
            "len": str(len(body_html)),
            "activity_list[0][id]": "ttv",
            "activity_list[0][is_checked]": "1",
            "activity_list[1][id]": "reward",
            "activity_list[1][is_checked]": "1",
            "activity_list[2][id]": "aigc_bjh_status",
            "activity_list[2][is_checked]": "0",
            "source_reprinted_allow": "0",
            "cover_image_source[wide_cover_image_source]": "text",
            "abstract_from": "3",
            "isBeautify": "false",
            "usingImgFilter": "false",
            "cover_layout": "one",
            "cover_images": cover_images_json,
            "_cover_images_map": cover_map_json,
            "cover_source": "upload",
            "subtitle": "",
            "bjhtopic_id": "",
            "bjhtopic_info": "",
            "clue": "",
            "bjhmt": "",
            "order_id": "",
            "aigc_rebuild": "",
            "image_edit_point": json.dumps([
                {
                    "img_type": "cover",
                    "img_num": {"template": 0, "font": 0, "filter": 0, "paster": 0, "cut": 0, "any": 0},
                },
                {
                    "img_type": "body",
                    "img_num": {"template": 0, "font": 0, "filter": 0, "paster": 0, "cut": 0, "any": 0},
                },
            ]),
            "article_id": bjh_article_id,
        }
        if cate_d1:
            form_data["cate_user_cms[0]"] = cate_d1
        if cate_d2:
            form_data["cate_user_cms[1]"] = cate_d2

        cookies = _parse_cookies(cookie)
        referer = f"{_EDIT_PAGE_URL}?type=news&article_id={bjh_article_id}"
        async with httpx.AsyncClient(
            cookies=cookies,
            headers=_COMMON_HEADERS,
            timeout=timeout,
        ) as client:
            resp = await client.post(
                _PUBLISH_URL,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": _BJH_BASE,
                    "Referer": referer,
                    "Token": edit_token,
                },
                params={"type": "news", "callback": "bjhpublish"},
                data=form_data,
            )
            resp.raise_for_status()
            text = resp.text
            if text.startswith("bjhpublish("):
                text = text[11:-1]
            return json.loads(text)

    async def check_cookie(self, cookie: str) -> bool:
        """
        检测 Cookie 是否有效（PRD §PUB-01）。
        尝试从编辑页提取 JWT Token；成功返回 True，否则返回 False。
        """
        try:
            await self.get_edit_token(cookie, timeout=15.0)
            return True
        except Exception:
            return False

    @staticmethod
    def md_to_html(md_text: str) -> str:
        """Markdown → 百家号兼容 HTML（对齐 v7 legacy 转换逻辑）。"""
        parts: list[str] = []
        for line in md_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("### "):
                parts.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                parts.append(f"<h3>{line[3:]}</h3>")
            elif line.startswith("# "):
                parts.append(f"<h2>{line[2:]}</h2>")
            else:
                line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
                parts.append(f"<p>{line}</p>")
        return "".join(parts)


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
