"""
单元测试：account_service.py 中不依赖 DB 的纯函数。
涵盖 Cookie 脱敏、导出加密/解密逻辑。
"""
import pytest

from app.core.exceptions import ValidationException
from app.services.account_service import (
    _decrypt_import,
    _derive_key,
    _encrypt_export,
    _mask_cookie,
)


# ── _mask_cookie ──────────────────────────────────────────────────────────────

def test_mask_cookie_shows_bduss_suffix():
    cookie = "BDUSS=ABCDEFGHIJ123456; STOKEN=xyz"
    result = _mask_cookie(cookie)
    assert result.startswith("BDUSS=***")
    # 末 6 位应当出现
    assert "123456" in result


def test_mask_cookie_short_bduss():
    cookie = "BDUSS=AB; OTHER=foo"
    result = _mask_cookie(cookie)
    assert "BDUSS=***" in result


def test_mask_cookie_no_bduss():
    cookie = "STOKEN=xyz"
    result = _mask_cookie(cookie)
    assert result == "BDUSS=***"


# ── _derive_key ───────────────────────────────────────────────────────────────

def test_derive_key_length():
    import os
    salt = os.urandom(16)
    key = _derive_key("my_passphrase", salt)
    assert len(key) == 32


def test_derive_key_deterministic():
    salt = b"\x00" * 16
    key1 = _derive_key("pass", salt)
    key2 = _derive_key("pass", salt)
    assert key1 == key2


def test_derive_key_different_passphrase():
    salt = b"\x00" * 16
    k1 = _derive_key("pass1", salt)
    k2 = _derive_key("pass2", salt)
    assert k1 != k2


# ── _encrypt_export / _decrypt_import ────────────────────────────────────────

def test_export_import_roundtrip():
    payload = {
        "version": 1,
        "accounts": [{"name": "test", "cookie": "BDUSS=abc", "categories": ["图书教育"]}],
    }
    passphrase = "my_secure_passphrase"
    encrypted = _encrypt_export(payload, passphrase)
    assert isinstance(encrypted, str)

    recovered = _decrypt_import(encrypted, passphrase)
    assert recovered == payload


def test_import_wrong_passphrase_raises():
    payload = {"version": 1, "accounts": []}
    encrypted = _encrypt_export(payload, "correct_passphrase")
    with pytest.raises(ValidationException, match="解密失败"):
        _decrypt_import(encrypted, "wrong_passphrase")


def test_import_corrupted_data_raises():
    with pytest.raises(ValidationException):
        _decrypt_import("bm90dmFsaWRkYXRh", "anypass")


def test_encrypt_export_different_each_call():
    """随机 salt + nonce 保证每次加密结果不同。"""
    payload = {"version": 1, "accounts": []}
    e1 = _encrypt_export(payload, "pass")
    e2 = _encrypt_export(payload, "pass")
    assert e1 != e2
