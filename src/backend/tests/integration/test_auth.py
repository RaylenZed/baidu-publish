"""
集成测试：POST /api/v1/auth/login

使用 starlette TestClient，覆盖 get_db（不需要真实数据库或 Redis）。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient

from app.core.database import get_db
from app.core.security import hash_password
from app.models.system_settings import SystemSettings

TEST_PASSWORD = "test_admin_password_123"


def _make_mock_session(
    password: str = TEST_PASSWORD,
    password_hash: str | None = None,
) -> AsyncMock:
    """构造返回 SystemSettings 的 mock AsyncSession。"""
    mock = AsyncMock()
    mock.get = AsyncMock(
        return_value=SystemSettings(
            id=1,
            admin_password_hash=password_hash if password_hash is not None else hash_password(password),
            token_version=1,
        )
    )
    return mock


@pytest.fixture
def client():
    """
    提供同步 TestClient，覆盖：
      - get_db → mock session
      - init_db / close_db → AsyncMock
      - 登录限流 → AsyncMock
    """
    from app.main import app

    async def override_get_db():
        yield _make_mock_session()

    app.dependency_overrides[get_db] = override_get_db

    with (
        patch("app.main.init_db", new=AsyncMock()),
        patch("app.main.close_db", new=AsyncMock()),
        patch("app.api.routes.auth.check_login_rate_limit", new=AsyncMock()),
        patch("app.api.routes.auth.reset_login_rate_limit", new=AsyncMock()),
    ):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    app.dependency_overrides.pop(get_db, None)


# ── 登录成功 ──────────────────────────────────────────────────────────────────

def test_login_success(client: TestClient):
    resp = client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "access_token" in body["data"]
    assert body["data"]["access_token"]


def test_login_returns_expires_at(client: TestClient):
    resp = client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
    assert resp.status_code == 200
    assert "expires_at" in resp.json()["data"]


# ── 登录失败 ──────────────────────────────────────────────────────────────────

def test_login_wrong_password(client: TestClient):
    resp = client.post("/api/v1/auth/login", json={"password": "wrong_password"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["success"] is False


def test_login_empty_password(client: TestClient):
    resp = client.post("/api/v1/auth/login", json={"password": ""})
    # 空密码不匹配 bcrypt hash → 401
    assert resp.status_code in (401, 422)


# ── 请求格式校验 ──────────────────────────────────────────────────────────────

def test_login_missing_password_field(client: TestClient):
    resp = client.post("/api/v1/auth/login", json={})
    assert resp.status_code == 422  # Pydantic 校验失败


def test_login_with_invalid_hash_returns_401(client: TestClient):
    """数据库哈希异常时不应抛 500，应按密码错误返回 401。"""
    from app.main import app

    async def override_get_db():
        yield _make_mock_session(password_hash="not_a_valid_bcrypt_hash")

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        resp = client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        assert resp.status_code == 401
        assert resp.json()["success"] is False
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)
