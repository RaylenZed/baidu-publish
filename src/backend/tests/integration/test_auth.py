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


def _make_mock_session(password: str = TEST_PASSWORD) -> AsyncMock:
    """构造返回 SystemSettings 的 mock AsyncSession。"""
    mock = AsyncMock()
    mock.get = AsyncMock(
        return_value=SystemSettings(
            id=1,
            admin_password_hash=hash_password(password),
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
