"""
系统设置服务（PRD §6.6）。

职责：
  - 读取 system_settings 单行配置
  - 批量更新运行参数
  - 修改管理员密码（同时递增 token_version，使所有旧 JWT 失效）
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedException, ValidationException
from app.core.security import hash_password, verify_password
from app.models.system_settings import SystemSettings
from app.schemas.settings import UpdateSettingsRequest


class SettingsService:

    async def get_settings(self, db: AsyncSession) -> SystemSettings:
        """获取 Singleton 配置行，不存在时抛异常（正常情况下首次启动已 seed）。"""
        row = await db.get(SystemSettings, 1)
        if row is None:
            raise ValidationException("系统配置未初始化，请重启服务以自动创建默认配置")
        return row

    async def update_settings(
        self,
        db: AsyncSession,
        data: UpdateSettingsRequest,
    ) -> SystemSettings:
        """
        批量更新运行参数。只更新请求中明确传入的字段（exclude_unset）。
        wecom_webhook="" 视为清除（存 None）。
        """
        row = await self.get_settings(db)

        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            # 空字符串 webhook 视为清除配置
            if field == "wecom_webhook" and value == "":
                value = None
            setattr(row, field, value)

        await db.flush()
        await db.refresh(row)
        return row

    async def change_password(
        self,
        db: AsyncSession,
        old_password: str,
        new_password: str,
    ) -> None:
        """
        修改管理员密码（PRD §6.6 / CLAUDE.md §3 #12）。

        流程：
          1. 验证 old_password 与当前 bcrypt 哈希匹配
          2. 用 bcrypt 哈希 new_password 并存储
          3. token_version += 1，使所有已签发 JWT 立即失效
        """
        row = await self.get_settings(db)

        if not verify_password(old_password, row.admin_password_hash):
            raise UnauthorizedException("原密码错误")

        row.admin_password_hash = hash_password(new_password)
        row.token_version += 1
        await db.flush()
