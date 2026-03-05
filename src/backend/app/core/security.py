"""
认证与加密工具（JWT、bcrypt、ws_ticket、Cookie AES 加解密）。

JWT 失效机制：token_version 存于 system_settings.token_version，
修改密码时 +1，鉴权时比对 token 中的 version 字段。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── 密码哈希 ─────────────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(sub: str, token_version: int) -> tuple[str, datetime]:
    """
    返回 (token, expires_at)。
    payload 包含 version 字段用于失效检测。
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": sub, "exp": expire, "version": token_version}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expire


def decode_access_token(token: str) -> dict:
    """解码并验证 token；失败抛 JWTError。"""
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


# ── WebSocket 一次性票据 ──────────────────────────────────────────────────────

WS_TICKET_PREFIX = "ws_ticket:"


def generate_ws_ticket() -> str:
    """生成 60 秒有效的一次性票据（存 Redis，由 ws_ticket 路由签发）。"""
    return secrets.token_urlsafe(32)


# ── Cookie AES-256-CBC 加解密 ────────────────────────────────────────────────

def _get_aes_key() -> bytes:
    """从 hex 字符串环境变量解析 32 字节密钥。"""
    key_hex = settings.COOKIE_SECRET_KEY
    return bytes.fromhex(key_hex)


def encrypt_cookie(plaintext: str) -> str:
    """AES-256-GCM 加密，返回 base64 编码字符串（nonce+ciphertext+tag）。"""
    key = _get_aes_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_cookie(encrypted: str) -> str:
    """AES-256-GCM 解密，返回明文 Cookie 字符串。"""
    key = _get_aes_key()
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
