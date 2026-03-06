"""
账号管理服务（PRD §6.2 / ACC-01~05）。

安全设计：
  - Cookie 存储前 AES-256-GCM 加密（core/security.py）
  - 导出文件 PBKDF2-HMAC-SHA256 派生密钥 + AES-256-GCM 加密
  - 响应中只返回脱敏 Cookie（BDUSS 末 6 位）
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CookieStatus, TaskStatus
from app.core.exceptions import (
    AccountCookieExpiredException,
    AccountHasPendingTasksException,
    AccountNameDuplicateException,
    AccountNotFoundException,
    ValidationException,
)
from app.core.logging import get_logger
from app.core.security import decrypt_cookie, encrypt_cookie
from app.models.account import Account
from app.models.task import Task
from app.schemas.account import (
    CheckAllResult,
    CookieCheckResult,
    CreateAccountRequest,
    ExportResponse,
    ImportResult,
    UpdateAccountRequest,
)
from app.services.category_service import CategoryService

logger = get_logger(__name__)
_category_svc = CategoryService()

# ── 加密常量 ──────────────────────────────────────────────────────────────────

_PBKDF2_SALT_LEN = 16
_PBKDF2_ITERATIONS = 100_000
_AES_NONCE_LEN = 12


def _mask_cookie(cookie: str) -> str:
    """提取 BDUSS 值并脱敏展示末 6 位，其余字段隐藏。"""
    m = re.search(r"BDUSS=([^;]+)", cookie)
    if m:
        bduss = m.group(1).strip()
        suffix = bduss[-6:] if len(bduss) >= 6 else bduss
        return f"BDUSS=***{suffix}"
    return "BDUSS=***"


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256 从用户口令派生 32 字节 AES 密钥。"""
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=32,
    )


def _encrypt_export(payload: dict, passphrase: str) -> bytes:
    """将 payload 加密为二进制：salt(16) + nonce(12) + ciphertext。"""
    salt = os.urandom(_PBKDF2_SALT_LEN)
    nonce = os.urandom(_AES_NONCE_LEN)
    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, json.dumps(payload, ensure_ascii=False).encode(), None)
    return base64.b64encode(salt + nonce + ciphertext).decode()


def _decrypt_import(encrypted_b64: str, passphrase: str) -> dict:
    """解密由 _encrypt_export 生成的数据，失败抛 ValidationException。"""
    try:
        raw = base64.b64decode(encrypted_b64)
        salt = raw[:_PBKDF2_SALT_LEN]
        nonce = raw[_PBKDF2_SALT_LEN: _PBKDF2_SALT_LEN + _AES_NONCE_LEN]
        ciphertext = raw[_PBKDF2_SALT_LEN + _AES_NONCE_LEN:]
        key = _derive_key(passphrase, salt)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext)
    except Exception:
        raise ValidationException("解密失败，口令错误或数据已损坏")


# ── AccountService ────────────────────────────────────────────────────────────


class AccountService:

    # ── 查询 ─────────────────────────────────────────────────────────────────

    async def list_accounts(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 20,
        keyword: str | None = None,
    ) -> tuple[list[Account], int]:
        """返回 (accounts, total)，支持分页与关键词搜索。"""
        stmt = select(Account)
        if keyword:
            stmt = stmt.where(Account.name.ilike(f"%{keyword}%"))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total: int = (await db.scalar(count_stmt)) or 0
        stmt = stmt.order_by(Account.created_at.asc()).offset((page - 1) * size).limit(size)
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_account(self, db: AsyncSession, account_id: int) -> Account:
        account = await db.get(Account, account_id)
        if account is None:
            raise AccountNotFoundException(account_id)
        return account

    # ── 创建 ─────────────────────────────────────────────────────────────────

    async def create_account(
        self,
        db: AsyncSession,
        data: CreateAccountRequest,
    ) -> Account:
        categories = await _category_svc.validate_category_names(
            db,
            data.categories,
            min_count=1,
            max_count=2,
            enabled_only=True,
        )
        account = Account(
            name=data.name,
            cookie_encrypted=encrypt_cookie(data.cookie),
            categories=categories,
            cookie_status=CookieStatus.UNCHECKED,
        )
        db.add(account)
        try:
            await db.flush()   # 在当前事务内写入，触发 DB 唯一约束
            await db.refresh(account)
        except IntegrityError:
            await db.rollback()
            raise AccountNameDuplicateException(data.name)
        return account

    # ── 更新 ─────────────────────────────────────────────────────────────────

    async def update_account(
        self,
        db: AsyncSession,
        account_id: int,
        data: UpdateAccountRequest,
    ) -> Account:
        account = await self.get_account(db, account_id)

        if data.name is not None:
            account.name = data.name
        if data.cookie is not None:
            account.cookie_encrypted = encrypt_cookie(data.cookie)
            account.cookie_status = CookieStatus.UNCHECKED   # 更新后重置状态
            account.cookie_checked_at = None
        if data.categories is not None:
            account.categories = await _category_svc.validate_category_names(
                db,
                data.categories,
                min_count=1,
                max_count=2,
                enabled_only=True,
            )

        try:
            await db.flush()
            await db.refresh(account)
        except IntegrityError:
            await db.rollback()
            raise AccountNameDuplicateException(data.name or account.name)
        return account

    # ── 删除 ─────────────────────────────────────────────────────────────────

    async def delete_account(self, db: AsyncSession, account_id: int) -> None:
        account = await self.get_account(db, account_id)

        # ACC-05：有未完成任务时拒绝删除
        pending_count = await db.scalar(
            select(func.count()).where(
                and_(
                    Task.account_id == account_id,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
            )
        )
        if pending_count and pending_count > 0:
            raise AccountHasPendingTasksException(account_id)

        await db.delete(account)
        await db.flush()

    # ── Cookie 检测 ───────────────────────────────────────────────────────────

    async def check_cookie(
        self,
        db: AsyncSession,
        account_id: int,
    ) -> CookieCheckResult:
        """
        检测单个账号 Cookie 有效性（PRD §6.2.3）。
        调用 BjhService.check_cookie（内部调用 refresh_token 接口）。
        """
        from app.services.bjh_service import BjhService

        account = await self.get_account(db, account_id)
        plain_cookie = decrypt_cookie(account.cookie_encrypted)

        bjh = BjhService()
        is_active = await bjh.check_cookie(plain_cookie)

        account.cookie_status = CookieStatus.ACTIVE if is_active else CookieStatus.EXPIRED
        account.cookie_checked_at = datetime.now(timezone.utc)
        await db.flush()

        if not is_active:
            logger.warning("Cookie 已过期", extra={"account_id": account_id})
            # Cookie 失效企微告警（NOTIF-04）
            try:
                from app.services.notify_service import NotifyService
                await NotifyService().send_cookie_expired(db, account.name)
            except Exception:
                pass  # 通知失败不影响检测结果

        return CookieCheckResult(
            account_id=account.id,
            name=account.name,
            cookie_status=account.cookie_status,
            checked_at=account.cookie_checked_at,
        )

    async def check_all_cookies(self, db: AsyncSession) -> CheckAllResult:
        """顺序检测所有账号，单个失败不中断整体。"""
        accounts, _ = await self.list_accounts(db, size=1000)
        results: list[CookieCheckResult] = []
        active = expired = 0

        for account in accounts:
            try:
                result = await self.check_cookie(db, account.id)
                results.append(result)
                if result.cookie_status == CookieStatus.ACTIVE:
                    active += 1
                else:
                    expired += 1
            except Exception as exc:
                logger.error(
                    "批量检测 Cookie 失败",
                    extra={"account_id": account.id, "error": str(exc)},
                )
                results.append(
                    CookieCheckResult(
                        account_id=account.id,
                        name=account.name,
                        cookie_status=CookieStatus.EXPIRED,
                        checked_at=datetime.now(timezone.utc),
                    )
                )
                expired += 1

        return CheckAllResult(
            total=len(accounts),
            active=active,
            expired=expired,
            results=results,
        )

    # ── 导出 ─────────────────────────────────────────────────────────────────

    async def export_accounts(
        self,
        db: AsyncSession,
        passphrase: str,
    ) -> ExportResponse:
        """
        导出全部账号为加密 JSON（PBKDF2-HMAC-SHA256 + AES-256-GCM）。
        导出数据包含明文 Cookie（解密后），供迁移/备份使用。
        """
        accounts, _ = await self.list_accounts(db, size=1000)
        payload = {
            "version": 1,
            "accounts": [
                {
                    "name": a.name,
                    "cookie": decrypt_cookie(a.cookie_encrypted),
                    "categories": a.categories,
                }
                for a in accounts
            ],
        }
        encrypted_b64 = _encrypt_export(payload, passphrase)
        return ExportResponse(
            data=encrypted_b64,
            count=len(accounts),
        )

    # ── 导入 ─────────────────────────────────────────────────────────────────

    async def import_accounts(
        self,
        db: AsyncSession,
        encrypted_b64: str,
        passphrase: str,
    ) -> ImportResult:
        """
        解密并批量 upsert 账号。
        重复 name → 更新 cookie/categories（不改变 cookie_status）。
        """
        payload = _decrypt_import(encrypted_b64, passphrase)

        if not isinstance(payload, dict) or "accounts" not in payload:
            raise ValidationException("导入数据格式错误，缺少 accounts 字段")

        items: list[dict] = payload["accounts"]
        created = updated = failed = 0
        details: list[dict] = []

        for item in items:
            name = item.get("name", "")
            cookie = item.get("cookie", "")
            categories = item.get("categories", [])

            # 基础校验
            if not name or "BDUSS=" not in cookie:
                failed += 1
                details.append({"name": name, "reason": "name 为空或 Cookie 缺少 BDUSS="})
                continue
            try:
                normalized_categories = await _category_svc.validate_category_names(
                    db,
                    categories,
                    min_count=1,
                    max_count=2,
                    enabled_only=True,
                )
            except ValidationException as exc:
                failed += 1
                details.append({"name": name, "reason": exc.message})
                continue

            # Upsert —— 每条使用 SAVEPOINT，失败只回滚当条，不影响已成功的条目
            existing = await db.scalar(select(Account).where(Account.name == name))
            try:
                async with db.begin_nested():
                    if existing:
                        existing.cookie_encrypted = encrypt_cookie(cookie)
                        existing.categories = normalized_categories
                        await db.flush()
                        updated += 1
                    else:
                        db.add(
                            Account(
                                name=name,
                                cookie_encrypted=encrypt_cookie(cookie),
                                categories=normalized_categories,
                                cookie_status=CookieStatus.UNCHECKED,
                            )
                        )
                        await db.flush()
                        created += 1
            except Exception as exc:
                failed += 1
                details.append({"name": name, "reason": str(exc)})

        return ImportResult(created=created, updated=updated, failed=failed, details=details)

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    @staticmethod
    def to_response(account: Account) -> dict:
        """将 Account ORM 对象转换为响应字典（含脱敏 cookie）。"""
        plain = decrypt_cookie(account.cookie_encrypted)
        return {
            "id": account.id,
            "name": account.name,
            "cookie_masked": _mask_cookie(plain),
            "categories": account.categories,
            "cookie_status": account.cookie_status,
            "cookie_checked_at": account.cookie_checked_at,
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }
