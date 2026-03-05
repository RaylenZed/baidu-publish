"""
单元测试：app/core/security.py 纯函数。
不需要数据库或 Redis，直接测试加密/JWT 逻辑。
"""
import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_cookie,
    encrypt_cookie,
    hash_password,
    verify_password,
)


# ── 密码哈希 ──────────────────────────────────────────────────────────────────

def test_hash_and_verify_password_success():
    plain = "my_secure_password"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True


def test_verify_password_wrong_input():
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


# ── Cookie 加解密 ─────────────────────────────────────────────────────────────

def test_encrypt_decrypt_cookie_roundtrip():
    original = "BDUSS=abcdef123456; STOKEN=xyz789"
    encrypted = encrypt_cookie(original)
    assert encrypted != original
    assert decrypt_cookie(encrypted) == original


def test_encrypt_cookie_produces_different_ciphertext():
    """AES-GCM 使用随机 nonce，每次加密结果不同。"""
    cookie = "BDUSS=test"
    c1 = encrypt_cookie(cookie)
    c2 = encrypt_cookie(cookie)
    assert c1 != c2  # 不同 nonce 产生不同密文


def test_decrypt_cookie_invalid_data_raises():
    with pytest.raises(Exception):
        decrypt_cookie("not_valid_base64_or_ciphertext!!!")


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_create_and_decode_token():
    token, expires_at = create_access_token("admin", token_version=1)
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"
    assert payload["version"] == 1


def test_token_version_stored_in_payload():
    token, _ = create_access_token("admin", token_version=42)
    payload = decode_access_token(token)
    assert payload["version"] == 42


def test_decode_invalid_token_raises_jwt_error():
    with pytest.raises(JWTError):
        decode_access_token("completely.invalid.token")


def test_decode_tampered_token_raises():
    token, _ = create_access_token("admin", token_version=1)
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(JWTError):
        decode_access_token(tampered)
