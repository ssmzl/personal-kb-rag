"""登录鉴权测试：密码哈希、JWT 签发/解析、登录接口成功/失败、受保护接口 401。

真实库接口测试需要配置 ``DATABASE_URL``（与 test_database.py 一致），
未配置时自动跳过；密码与 JWT 单测不依赖数据库。
"""

import uuid
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.config import settings
from app.database import async_session_factory, engine, init_database
from app.main import app
from app.models import User
from app.services import auth_service
from app.exceptions import BizException

TEST_PASSWORD = "test-password-123"


@pytest.fixture
def jwt_settings(monkeypatch: pytest.MonkeyPatch):
    """为 auth_service 注入测试用 JWT 配置（settings 为 frozen dataclass，用 replace 替换）。"""
    test_settings = replace(settings, jwt_secret="test-jwt-secret", jwt_expire_minutes=60)
    monkeypatch.setattr(auth_service, "settings", test_settings)
    return test_settings


# ---------- 密码哈希 ----------

def test_password_hash_roundtrip() -> None:
    """bcrypt 哈希可校验通过，错误密码不通过。"""
    password_hash = auth_service.hash_password(TEST_PASSWORD)

    assert password_hash != TEST_PASSWORD
    assert auth_service.verify_password(TEST_PASSWORD, password_hash)
    assert not auth_service.verify_password("wrong-password", password_hash)


def test_password_hash_over_72_bytes_consistent() -> None:
    """超长密码在哈希与校验两侧截断策略一致，校验仍可通过。"""
    long_password = "a" * 100
    password_hash = auth_service.hash_password(long_password)

    assert auth_service.verify_password(long_password, password_hash)
    assert not auth_service.verify_password("a" * 71 + "b", password_hash)


def test_verify_password_with_invalid_hash_returns_false() -> None:
    """非法哈希串不抛异常，按校验失败处理。"""
    assert not auth_service.verify_password(TEST_PASSWORD, "not-a-bcrypt-hash")


# ---------- JWT 签发 / 解析 ----------

def test_jwt_roundtrip(jwt_settings) -> None:
    """签发的 token 可解析出 user id 与 username。"""
    user = User(id=1, username="tester", password_hash="x")
    token, expires_in = auth_service.create_access_token(user)

    assert expires_in == 3600
    payload = auth_service.decode_access_token(token)
    assert payload["sub"] == "1"
    assert payload["username"] == "tester"


def test_jwt_decode_tampered_token_rejected(jwt_settings) -> None:
    """篡改的 token 解析抛 401 业务异常。"""
    user = User(id=1, username="tester", password_hash="x")
    token, _ = auth_service.create_access_token(user)

    with pytest.raises(BizException) as exc_info:
        auth_service.decode_access_token(token[:-2] + "xx")
    assert exc_info.value.http_status == 401


def test_jwt_decode_expired_token_rejected(jwt_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """过期 token 解析抛 401 业务异常。"""
    expired_settings = replace(jwt_settings, jwt_expire_minutes=-1)
    monkeypatch.setattr(auth_service, "settings", expired_settings)
    user = User(id=1, username="tester", password_hash="x")
    token, _ = auth_service.create_access_token(user)

    with pytest.raises(BizException) as exc_info:
        auth_service.decode_access_token(token)
    assert exc_info.value.http_status == 401


def test_jwt_missing_secret_raises_biz_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 JWT_SECRET 时签发返回业务异常而非 500。"""
    no_secret = replace(settings, jwt_secret="")
    monkeypatch.setattr(auth_service, "settings", no_secret)
    user = User(id=1, username="tester", password_hash="x")

    with pytest.raises(BizException) as exc_info:
        auth_service.create_access_token(user)
    assert "JWT_SECRET" in exc_info.value.message


# ---------- 登录接口（真实库） ----------

requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="未配置 DATABASE_URL，跳过真实库测试",
)


@pytest.fixture
async def test_user(jwt_settings):
    """在真实库中创建一个已知密码的测试用户，测试后清理。"""
    await init_database()
    assert async_session_factory is not None

    username = f"auth_test_{uuid.uuid4().hex[:12]}"
    async with async_session_factory() as session:
        session.add(User(username=username, password_hash=auth_service.hash_password(TEST_PASSWORD)))
        await session.commit()

    yield username

    async with async_session_factory() as session:
        await session.execute(delete(User).where(User.username == username))
        await session.commit()

    # 每个 async 测试运行在独立事件循环，释放连接池避免跨循环复用残留连接
    if engine is not None:
        await engine.dispose()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@requires_db
async def test_login_success_returns_token(client: AsyncClient, test_user: str) -> None:
    """正确账号密码登录成功，返回统一结构包裹的 token，并可访问受保护接口。"""
    response = await client.post(
        "/api/auth/login",
        json={"username": test_user, "password": TEST_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    token = body["data"]["token"]
    assert token
    assert body["data"]["username"] == test_user

    # 携带 token 访问受保护接口成功
    me_response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["code"] == 0
    assert me_body["data"]["username"] == test_user


@requires_db
async def test_login_wrong_password_returns_unified_error(
    client: AsyncClient,
    test_user: str,
) -> None:
    """错误密码返回统一错误体，不区分账号不存在/密码错误。"""
    response = await client.post(
        "/api/auth/login",
        json={"username": test_user, "password": "wrong-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 40001
    assert body["message"] == "账号或密码错误"

    # 不存在的账号返回相同的错误体
    response2 = await client.post(
        "/api/auth/login",
        json={"username": "no_such_user", "password": "whatever"},
    )
    body2 = response2.json()
    assert body2["code"] == body["code"]
    assert body2["message"] == body["message"]


@requires_db
async def test_protected_endpoint_without_token_returns_401(client: AsyncClient) -> None:
    """未携带 / 携带非法 token 访问受保护接口返回 401 统一错误体。"""
    no_token = await client.get("/api/auth/me")
    assert no_token.status_code == 401
    assert no_token.json()["code"] == 40100

    bad_token = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert bad_token.status_code == 401
    assert bad_token.json()["code"] == 40100
