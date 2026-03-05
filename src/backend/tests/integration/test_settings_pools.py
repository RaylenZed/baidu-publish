"""
集成测试：settings / pools 路由关键场景。

目标：
1. 覆盖设置页完整字段更新接口
2. 覆盖变量池品类约束与成功更新路径
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.api.deps import get_current_user
from app.core.constants import AigcModel, NotifyLevel, PoolType, TaskMode
from app.core.database import get_db


def _make_mock_session() -> AsyncMock:
    """构造最小化 AsyncSession mock。"""
    mock = AsyncMock()
    mock.commit = AsyncMock()
    return mock


@pytest.fixture
def client():
    """
    提供同步 TestClient，覆盖：
      - get_db：mock session
      - get_current_user：固定管理员身份
      - init_db / close_db：避免触发真实连接
    """
    from app.main import app

    async def override_get_db():
        yield _make_mock_session()

    async def override_get_current_user():
        return {"sub": "admin", "version": 1}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with (
        patch("app.main.init_db", new=AsyncMock()),
        patch("app.main.close_db", new=AsyncMock()),
    ):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_get_categories_returns_18_items(client: TestClient):
    resp = client.get("/api/v1/settings/categories")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 18
    assert "图书教育" in body["data"]


def test_update_settings_full_payload_success(client: TestClient):
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        id=1,
        run_mode=TaskMode.PUBLISH,
        aigc_model=AigcModel.DS_V3,
        account_delay=20,
        max_concurrent_accounts=2,
        daily_limit=5,
        task_timeout_minutes=30,
        generate_timeout=180,
        polish_timeout=180,
        cover_timeout=45,
        publish_timeout=45,
        draft_timeout=45,
        wecom_webhook="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        notify_level=NotifyLevel.ALL,
        updated_at=now,
    )

    payload = {
        "run_mode": "publish",
        "aigc_model": "ds_v3",
        "account_delay": 20,
        "max_concurrent_accounts": 2,
        "daily_limit": 5,
        "task_timeout_minutes": 30,
        "generate_timeout": 180,
        "polish_timeout": 180,
        "cover_timeout": 45,
        "publish_timeout": 45,
        "draft_timeout": 45,
        "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        "notify_level": "all",
    }

    with patch("app.api.routes.settings._svc.update_settings", new=AsyncMock(return_value=row)) as mock_update:
        resp = client.put("/api/v1/settings", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["run_mode"] == "publish"
    assert body["data"]["account_delay"] == 20
    assert body["data"]["cover_timeout"] == 45
    assert body["data"]["notify_level"] == "all"
    mock_update.assert_awaited_once()


def test_update_angle_pool_without_category_returns_422(client: TestClient):
    resp = client.put(
        "/api/v1/pools/angle",
        json={"items": [{"value": "角度A", "weight": 1, "enabled": True}]},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["errorCode"] == "VALIDATION_ERROR"
    assert "品类专属池" in body["message"]


def test_update_style_pool_success_and_ignore_category(client: TestClient):
    now = datetime.now(timezone.utc)
    pool = SimpleNamespace(
        id=100,
        pool_type=PoolType.STYLE,
        category=None,  # 通用池 category 强制为 null
        items=[{"value": "专业测评风", "weight": 3, "enabled": True}],
        updated_at=now,
    )

    payload = {
        "category": "图书教育",  # 即便传入，通用池也应忽略
        "items": [{"value": "专业测评风", "weight": 3, "enabled": True}],
    }

    with patch("app.api.routes.pools._svc.update_pool", new=AsyncMock(return_value=pool)) as mock_update:
        resp = client.put("/api/v1/pools/style", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["pool_type"] == "style"
    assert body["data"]["category"] is None
    mock_update.assert_awaited_once()
