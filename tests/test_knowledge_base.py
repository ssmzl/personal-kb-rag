"""知识库管理接口测试：创建、列表文档数、重命名、删除级联、越权访问。

真实库接口测试需要配置 ``DATABASE_URL``（与 test_auth.py 一致），
未配置时自动跳过。
"""

import uuid
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.config import settings
from app.database import async_session_factory, engine, init_database
from app.main import app
from app.models import Document, DocumentChunk, KnowledgeBase, User
from app.services import auth_service

requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="未配置 DATABASE_URL，跳过真实库测试",
)

pytestmark = requires_db


@pytest.fixture
def jwt_settings(monkeypatch: pytest.MonkeyPatch):
    """为 auth_service 注入测试用 JWT 配置。"""
    test_settings = replace(settings, jwt_secret="test-jwt-secret", jwt_expire_minutes=60)
    monkeypatch.setattr(auth_service, "settings", test_settings)
    return test_settings


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def test_user(jwt_settings):
    """在真实库中创建测试用户并签发 token，测试后按 ID 清理（知识库随用户级联删除）。"""
    await init_database()
    assert async_session_factory is not None

    username = f"kb_test_{uuid.uuid4().hex[:12]}"
    async with async_session_factory() as session:
        user = User(username=username, password_hash="test-hash")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    token, _ = auth_service.create_access_token(
        User(id=user_id, username=username, password_hash="test-hash")
    )
    yield {"user_id": user_id, "headers": {"Authorization": f"Bearer {token}"}}

    async with async_session_factory() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()

    # 每个 async 测试运行在独立事件循环，释放连接池避免跨循环复用残留连接
    if engine is not None:
        await engine.dispose()


async def _create_kb_via_api(client: AsyncClient, headers: dict, name: str) -> int:
    """通过接口创建知识库并返回 kb_id。"""
    response = await client.post("/api/knowledge-bases", json={"name": name}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    return body["data"]["id"]


async def test_create_and_list_knowledge_base(client: AsyncClient, test_user: dict) -> None:
    """创建知识库成功，列表中包含该库且文档数为 0，时间字段为 yyyy-MM-dd HH:mm:ss。"""
    kb_id = await _create_kb_via_api(client, test_user["headers"], "我的第一个知识库")

    response = await client.get("/api/knowledge-bases", headers=test_user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0

    items = {item["id"]: item for item in body["data"]}
    assert kb_id in items
    item = items[kb_id]
    assert item["name"] == "我的第一个知识库"
    assert item["document_count"] == 0
    # 时间格式校验：yyyy-MM-dd HH:mm:ss（19 位，含空格分隔）
    assert len(item["create_time"]) == 19 and item["create_time"][10] == " "


async def test_create_knowledge_base_with_blank_name_rejected(
    client: AsyncClient,
    test_user: dict,
) -> None:
    """纯空白名称创建知识库返回统一参数校验错误。"""
    response = await client.post(
        "/api/knowledge-bases",
        json={"name": "   "},
        headers=test_user["headers"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == 42200


async def test_rename_knowledge_base(client: AsyncClient, test_user: dict) -> None:
    """重命名知识库后列表展示新名称。"""
    kb_id = await _create_kb_via_api(client, test_user["headers"], "旧名称")

    response = await client.put(
        f"/api/knowledge-bases/{kb_id}",
        json={"name": "新名称"},
        headers=test_user["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["name"] == "新名称"

    list_response = await client.get("/api/knowledge-bases", headers=test_user["headers"])
    items = {item["id"]: item for item in list_response.json()["data"]}
    assert items[kb_id]["name"] == "新名称"


async def test_delete_knowledge_base_cascades(client: AsyncClient, test_user: dict) -> None:
    """删除知识库后，其下文档与分块向量记录被级联清除，不影响其他知识库。"""
    headers = test_user["headers"]
    kb_id = await _create_kb_via_api(client, headers, "待删除知识库")
    other_kb_id = await _create_kb_via_api(client, headers, "保留知识库")

    # 直接在库中放入文档与分块（含 1024 维向量）
    assert async_session_factory is not None
    async with async_session_factory() as session:
        document = Document(
            kb_id=kb_id,
            filename="待删除文档.txt",
            file_path="uploads/kb_test.txt",
            file_type="txt",
            file_size=64,
        )
        session.add(document)
        await session.flush()
        session.add(
            DocumentChunk(
                kb_id=kb_id,
                document_id=document.id,
                chunk_index=0,
                content="测试分块内容",
                embedding=[0.0] * settings.embedding_dimension,
            )
        )
        await session.commit()

    response = await client.delete(f"/api/knowledge-bases/{kb_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["code"] == 0

    async with async_session_factory() as session:
        document_count = (
            await session.execute(select(func.count(Document.id)).where(Document.kb_id == kb_id))
        ).scalar_one()
        chunk_count = (
            await session.execute(
                select(func.count(DocumentChunk.id)).where(DocumentChunk.kb_id == kb_id)
            )
        ).scalar_one()
        assert document_count == 0
        assert chunk_count == 0

        remaining = await session.get(KnowledgeBase, other_kb_id)
        assert remaining is not None

    # 列表中不再出现被删除的知识库
    list_response = await client.get("/api/knowledge-bases", headers=headers)
    items = {item["id"]: item for item in list_response.json()["data"]}
    assert kb_id not in items
    assert other_kb_id in items


async def test_cannot_access_other_users_knowledge_base(client: AsyncClient, test_user: dict) -> None:
    """重命名/删除他人知识库返回 404 统一错误体。"""
    headers = test_user["headers"]
    kb_id = await _create_kb_via_api(client, headers, "用户A的知识库")

    # 第二个用户
    assert async_session_factory is not None
    other_username = f"kb_test_{uuid.uuid4().hex[:12]}"
    async with async_session_factory() as session:
        other = User(username=other_username, password_hash="test-hash")
        session.add(other)
        await session.commit()
        await session.refresh(other)
        other_id = other.id

    other_token, _ = auth_service.create_access_token(
        User(id=other_id, username=other_username, password_hash="test-hash")
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    try:
        rename_response = await client.put(
            f"/api/knowledge-bases/{kb_id}",
            json={"name": "越权重命名"},
            headers=other_headers,
        )
        assert rename_response.status_code == 404
        assert rename_response.json()["code"] == 40400

        delete_response = await client.delete(
            f"/api/knowledge-bases/{kb_id}",
            headers=other_headers,
        )
        assert delete_response.status_code == 404
        assert delete_response.json()["code"] == 40400

        # 越权删除未生效：知识库仍在
        list_response = await client.get("/api/knowledge-bases", headers=headers)
        items = {item["id"]: item for item in list_response.json()["data"]}
        assert kb_id in items
        assert items[kb_id]["name"] == "用户A的知识库"
    finally:
        async with async_session_factory() as session:
            await session.execute(delete(User).where(User.id == other_id))
            await session.commit()
