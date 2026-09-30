"""pytest 公共夹具：测试库隔离 + ASGI 客户端（含信封断言小工具）。"""

from __future__ import annotations

import os
from pathlib import Path

# 必须在导入 app 前设置：测试用独立 sqlite 文件
_TEST_DB = Path(__file__).parent / "_test_nasdeck.db"
os.environ["NASDECK_DB_URL"] = f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}"
os.environ.setdefault("NASDECK_API_KEY", "")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture(scope="session")
async def client():
    from app.db.init_db import init_db
    from main import app

    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    from app.db.session import engine

    await engine.dispose()
    _TEST_DB.unlink(missing_ok=True)


def ok(response) -> dict:
    """断言成功信封并返回 data（契约 §1.2）。"""
    body = response.json()
    assert response.status_code == 200, body
    assert body["code"] == 0, body
    assert "timestamp" in body
    return body["data"]


def err(response, code: int) -> dict:
    """断言业务错误信封（契约 §1.3：错误信封无 timestamp）。"""
    body = response.json()
    assert body["code"] == code, body
    assert body["data"] is None
    assert "timestamp" not in body
    return body
