"""
企微通知服务（PRD §NOTIF-01~04 / PRD §6.8 通知配置）

职责：
  - 任务失败告警（NOTIF-01）
  - 每日汇总通知（NOTIF-02，Beat 触发）
  - partial_content WARN 通知（NOTIF-03）
  - Cookie 失效告警（NOTIF-04）

通知级别（system_settings.notify_level）：
  - all          → 发送全部 4 类通知
  - failure_only → 仅发送 NOTIF-01 和 NOTIF-04（任务失败 + Cookie 失效）
  - off          → 不发送任何通知

企微 Webhook 格式：text 类型，content 为 markdown 文本。
"""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import NotifyLevel
from app.core.logging import get_logger

logger = get_logger(__name__)

_REQUEST_TIMEOUT = 10.0  # Webhook 请求超时（秒）


class NotifyService:
    """企业微信 Webhook 通知，调用前自动从 DB 读取 Webhook 配置。"""

    # ── 公开通知方法 ──────────────────────────────────────────────────────────

    async def send_task_failure(
        self,
        db: AsyncSession,
        task_id: int,
        account_name: str,
        error_message: str,
    ) -> None:
        """任务失败告警（NOTIF-01）。failure_only / all 级别均发送。"""
        webhook_url, level = await self._get_config(db)
        if not webhook_url or level == NotifyLevel.OFF:
            return

        text = (
            f"⚠️ 任务执行失败\n"
            f"**任务 ID**：{task_id}\n"
            f"**账号**：{account_name}\n"
            f"**原因**：{error_message}"
        )
        await self._post_webhook(webhook_url, text)

    async def send_daily_summary(self, db: AsyncSession, stats: dict) -> None:
        """
        每日汇总通知（NOTIF-02）。仅 all 级别发送，由 Beat 每日触发。

        stats 期望包含：
          total, success, failed, timeout, draft_saved, published
        """
        webhook_url, level = await self._get_config(db)
        if not webhook_url or level != NotifyLevel.ALL:
            return

        total = stats.get("total", 0)
        success = stats.get("success", 0)
        failed = stats.get("failed", 0)
        timeout = stats.get("timeout", 0)
        published = stats.get("published", 0)

        text = (
            f"📊 今日任务汇总\n"
            f"**总计**：{total} 个任务\n"
            f"✅ 成功：{success}  ❌ 失败：{failed}  ⏱️ 超时：{timeout}\n"
            f"📰 已发布：{published} 篇文章"
        )
        await self._post_webhook(webhook_url, text)

    async def send_content_warning(
        self,
        db: AsyncSession,
        task_id: int,
        article_id: int,
        warning: str,
    ) -> None:
        """
        内容风险告警（NOTIF-03）。仅 all 级别发送。
        partial_content 场景：SSE 截断，内容不完整，需人工确认后才可发布。
        """
        webhook_url, level = await self._get_config(db)
        if not webhook_url or level != NotifyLevel.ALL:
            return

        text = (
            f"🚨 内容风险告警（需人工处理）\n"
            f"**任务 ID**：{task_id}  **文章 ID**：{article_id}\n"
            f"**警告类型**：{warning}\n"
            f"内容不完整（partial_content），已降级为草稿，"
            f"请在文章管理页面人工确认后再发布。"
        )
        await self._post_webhook(webhook_url, text)

    async def send_cookie_expired(
        self, db: AsyncSession, account_name: str
    ) -> None:
        """Cookie 失效告警（NOTIF-04）。failure_only / all 级别均发送。"""
        webhook_url, level = await self._get_config(db)
        if not webhook_url or level == NotifyLevel.OFF:
            return

        text = (
            f"🔑 Cookie 已失效\n"
            f"**账号**：{account_name}\n"
            f"请在账号管理页面更新 Cookie，否则该账号无法继续执行任务。"
        )
        await self._post_webhook(webhook_url, text)

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    async def _get_config(
        self, db: AsyncSession
    ) -> tuple[str | None, NotifyLevel]:
        """从 system_settings 读取 webhook URL 和通知级别。"""
        from app.models.system_settings import SystemSettings
        row = await db.get(SystemSettings, 1)
        if row is None:
            return None, NotifyLevel.OFF
        return row.wecom_webhook, row.notify_level

    async def _post_webhook(self, webhook_url: str, content: str) -> None:
        """
        发送企微 Webhook（text 格式）。
        发送失败只记录日志，不向调用方抛异常（通知失败不影响业务流程）。
        """
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                resp = await client.post(webhook_url, json=payload)
                if resp.status_code != 200:
                    logger.warning(
                        "企微 Webhook 响应异常",
                        extra={"status": resp.status_code, "body": resp.text[:200]},
                    )
        except Exception as exc:
            logger.error(
                "企微 Webhook 发送失败",
                extra={"error": str(exc), "webhook": webhook_url[:50]},
            )
