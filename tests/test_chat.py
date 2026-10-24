"""RAG 流式问答测试。

覆盖：
- 提示词构造（强制依据资料、无命中提示）与对话消息拼接；
- DashScope 流式响应行解析；
- 会话增删改查与历史消息时间格式；
- 检索按知识库过滤、SSE 增量输出与 sources 事件、消息持久化；
- 大模型失败时先发 error 事件、未配置 API Key 的友好提示。

真实库接口测试需要配置 ``DATABASE_URL``（与 test_documents.py 一致），
未配置时自动跳过。
"""

import json
import uuid
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session_factory, engine, init_database
from app.exceptions import BizException
from app.main import app
from app.models import (
    CHAT_ROLE_ASSISTANT,
    CHAT_ROLE_USER,
    ChatMessage,
    Document,
    DocumentChunk,
    User,
)
from app.services import auth_service, chat_client, chat_service, embedding_client
from app.services.chat_service import (
    RetrievedChunk,
    build_chat_messages,
    build_system_prompt,
)

requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="未配置 DATABASE_URL，跳过真实库测试",
)


# ---------- 提示词与流式解析（无需数据库） ----------


def test_build_system_prompt_enforces_grounding_and_reference() -> None:
    """system prompt 强制仅依据资料回答，并携带文档名、片段与内容。"""
    chunk = RetrievedChunk(
        document_id=1,
        document_name="课程笔记.md",
        chunk_index=2,
        content="FastAPI 是基于 Python 的异步 Web 框架。",
    )

    prompt = build_system_prompt([chunk])

    assert "只能使用参考资料中的信息作答" in prompt
    assert "知识库中未找到相关内容" in prompt
    assert "课程笔记.md" in prompt
    assert "片段 3" in prompt
    assert chunk.content in prompt


def test_build_system_prompt_without_chunks_marks_not_found() -> None:
    """未检索到分块时，参考资料区明确标注未找到相关内容。"""
    prompt = build_system_prompt([])

    assert "（知识库未检索到与问题相关的内容）" in prompt
    assert "知识库中未找到相关内容" in prompt


def test_build_chat_messages_keeps_history_and_current_question() -> None:
    """消息顺序为 system → 历史正序 → 当前问题。"""
    history = [
        ChatMessage(id=1, session_id=1, role=CHAT_ROLE_USER, content="历史问题"),
        ChatMessage(id=2, session_id=1, role=CHAT_ROLE_ASSISTANT, content="历史回答"),
    ]

    messages = build_chat_messages(history, "新问题", [])

    assert messages[0]["role"] == "system"
    assert messages[1:] == [
        {"role": "user", "content": "历史问题"},
        {"role": "assistant", "content": "历史回答"},
        {"role": "user", "content": "新问题"},
    ]


def test_parse_stream_line_delta_and_done() -> None:
    """流式响应行可解析出增量文本与结束标记，忽略非数据行。"""
    line = 'data: {"choices": [{"delta": {"content": "你好"}}]}'

    assert chat_client.parse_stream_line(line) == "你好"
    assert chat_client.parse_stream_line("data: [DONE]") == chat_client.DONE_MARKER
    assert chat_client.parse_stream_line(": keep-alive") is None
    assert chat_client.parse_stream_line('data: {"choices": []}') is None


def test_parse_stream_line_error_payload_raises() -> None:
    """流内 error 负载转为业务异常，便于上层发送 error 事件。"""
    line = 'data: {"error": {"message": "quota exceeded"}}'

    with pytest.raises(BizException) as exc_info:
        chat_client.parse_stream_line(line)

    assert "quota exceeded" in exc_info.value.message


async def test_stream_chat_without_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 DASHSCOPE_API_KEY 时给出友好业务异常而非网络错误。"""
    monkeypatch.setattr(chat_client, "settings", replace(settings, dashscope_api_key=""))

    with pytest.raises(BizException) as exc_info:
        async for _ in chat_client.stream_chat_completion(
            [{"role": "user", "content": "你好"}]
        ):
            pass

    assert "AI 服务未配置" in exc_info.value.message


# ---------- 真实库接口 ----------


@pytest.fixture
def jwt_settings(monkeypatch: pytest.MonkeyPatch):
    """为 auth_service 注入测试用 JWT 配置。"""
    test_settings = replace(settings, jwt_secret="test-jwt-secret", jwt_expire_minutes=60)
    monkeypatch.setattr(auth_service, "settings", test_settings)
    return test_settings


@pytest.fixture
def fixed_embeddings(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Mock Embedding：任何文本都返回同一个单位向量，检索结果稳定。"""
    vector = [0.0] * settings.embedding_dimension
    vector[0] = 1.0

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [list(vector) for _ in texts]

    monkeypatch.setattr(embedding_client, "embed_texts", fake_embed_texts)
    return vector


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Mock 大模型流式输出，并记录收到的消息用于断言提示词拼接。"""
    captured: dict = {"messages": []}

    async def fake_stream(messages: list[dict[str, str]]):
        captured["messages"] = messages
        for token in ["FastAPI ", "是异步 ", "Web 框架。"]:
            yield token

    monkeypatch.setattr(chat_client, "stream_chat_completion", fake_stream)
    return captured


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def test_user(jwt_settings):
    """创建测试用户并签发 token，测试后按用户级联清理数据。"""
    await init_database()
    assert async_session_factory is not None

    username = f"chat_test_{uuid.uuid4().hex[:12]}"
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


async def _create_kb(client: AsyncClient, headers: dict, name: str) -> int:
    """通过接口创建知识库并返回 kb_id。"""
    response = await client.post("/api/knowledge-bases", json={"name": name}, headers=headers)
    assert response.status_code == 200
    return response.json()["data"]["id"]


async def _create_session(client: AsyncClient, kb_id: int, headers: dict) -> int:
    """通过接口新建会话并返回 session_id。"""
    response = await client.post(f"/api/knowledge-bases/{kb_id}/chat-sessions", json={}, headers=headers)
    assert response.status_code == 200
    return response.json()["data"]["id"]


async def _seed_document_chunk(kb_id: int, filename: str, content: str, vector: list[float]) -> None:
    """直接写入一份完成状态的文档与分块，用于检索与问答测试。"""
    assert async_session_factory is not None
    async with async_session_factory() as session:
        document = Document(
            kb_id=kb_id,
            filename=filename,
            file_path=f"uploads/{uuid.uuid4().hex}.txt",
            file_type="txt",
            file_size=len(content),
            status="completed",
            chunk_count=1,
        )
        session.add(document)
        await session.flush()
        session.add(
            DocumentChunk(
                kb_id=kb_id,
                document_id=document.id,
                chunk_index=0,
                content=content,
                embedding=vector,
            )
        )
        await session.commit()


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """把 SSE 文本解析为 (event, data) 列表。"""
    events: list[tuple[str, dict]] = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        assert data_lines, f"SSE 事件缺少 data：{block!r}"
        events.append((event, json.loads("\n".join(data_lines))))
    return events


@requires_db
async def test_session_crud_and_history_time_format(
    client: AsyncClient,
    test_user: dict,
) -> None:
    """会话可新建（默认标题）、重命名、删除；历史消息时间为统一格式。"""
    headers = test_user["headers"]
    kb_id = await _create_kb(client, headers, "会话测试库")

    create_response = await client.post(
        f"/api/knowledge-bases/{kb_id}/chat-sessions",
        json={},
        headers=headers,
    )
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["title"] == "新对话"
    session_id = created["id"]
    assert len(created["create_time"]) == 19 and created["create_time"][10] == " "

    list_response = await client.get(
        f"/api/knowledge-bases/{kb_id}/chat-sessions", headers=headers
    )
    assert [item["id"] for item in list_response.json()["data"]] == [session_id]

    rename_response = await client.put(
        f"/api/chat-sessions/{session_id}",
        json={"title": "重命名后的会话"},
        headers=headers,
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["data"]["title"] == "重命名后的会话"

    messages_response = await client.get(
        f"/api/chat-sessions/{session_id}/messages", headers=headers
    )
    assert messages_response.status_code == 200
    assert messages_response.json()["data"] == []

    delete_response = await client.delete(f"/api/chat-sessions/{session_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["code"] == 0

    list_response = await client.get(
        f"/api/knowledge-bases/{kb_id}/chat-sessions", headers=headers
    )
    assert list_response.json()["data"] == []


@requires_db
async def test_retrieve_chunks_filters_by_knowledge_base(
    client: AsyncClient,
    test_user: dict,
    fixed_embeddings: list[float],
) -> None:
    """检索只返回指定知识库内的分块，不串库。"""
    headers = test_user["headers"]
    kb_a = await _create_kb(client, headers, "检索库A")
    kb_b = await _create_kb(client, headers, "检索库B")
    await _seed_document_chunk(kb_a, "a.md", "A 库的内容", fixed_embeddings)
    await _seed_document_chunk(kb_b, "b.md", "B 库的内容", fixed_embeddings)

    assert async_session_factory is not None
    async with async_session_factory() as session:
        chunks_a = await chat_service.retrieve_chunks(session, kb_a, "任意问题")
        chunks_b = await chat_service.retrieve_chunks(session, kb_b, "任意问题")

    assert [chunk.document_name for chunk in chunks_a] == ["a.md"]
    assert [chunk.document_name for chunk in chunks_b] == ["b.md"]


@requires_db
async def test_ask_streams_answer_with_sources_and_persists(
    client: AsyncClient,
    test_user: dict,
    fixed_embeddings: list[float],
    fake_llm: dict,
) -> None:
    """问答 SSE 先增量输出、再发 sources，并把用户与助手消息持久化。"""
    headers = test_user["headers"]
    kb_id = await _create_kb(client, headers, "问答测试库")
    await _seed_document_chunk(
        kb_id,
        "课程笔记.md",
        "FastAPI 是基于 Python 的异步 Web 框架。",
        fixed_embeddings,
    )
    session_id = await _create_session(client, kb_id, headers)

    response = await client.post(
        f"/api/chat-sessions/{session_id}/ask",
        json={"question": "FastAPI 是什么？"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    assert [name for name, _ in events] == ["delta", "delta", "delta", "sources"]
    answer = "".join(data["content"] for name, data in events if name == "delta")
    assert answer == "FastAPI 是异步 Web 框架。"

    source_payload = events[-1][1]
    sources = source_payload["sources"]
    assert len(sources) == 1
    assert sources[0]["document_name"] == "课程笔记.md"
    assert sources[0]["chunk_index"] == 0
    assert "FastAPI" in sources[0]["content"]
    assert isinstance(source_payload["assistant_message_id"], int)

    # 送给模型的消息：system 携带资料，最后一条是当前问题
    llm_messages = fake_llm["messages"]
    assert llm_messages[0]["role"] == "system"
    assert "只能使用参考资料中的信息作答" in llm_messages[0]["content"]
    assert "FastAPI 是基于 Python 的异步 Web 框架。" in llm_messages[0]["content"]
    assert llm_messages[-1] == {"role": "user", "content": "FastAPI 是什么？"}

    # 历史消息已持久化，引用来源与时间格式正确
    history = (
        await client.get(f"/api/chat-sessions/{session_id}/messages", headers=headers)
    ).json()["data"]
    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "FastAPI 是什么？"
    assert history[1]["content"] == answer
    assert history[1]["sources"][0]["document_name"] == "课程笔记.md"
    assert len(history[1]["create_time"]) == 19 and history[1]["create_time"][10] == " "


@requires_db
async def test_ask_without_knowledge_chunks_uses_not_found_prompt(
    client: AsyncClient,
    test_user: dict,
    fixed_embeddings: list[float],
    fake_llm: dict,
) -> None:
    """知识库无分块时提示词明确告知未找到，sources 为空但不中断流。"""
    headers = test_user["headers"]
    kb_id = await _create_kb(client, headers, "空知识库")
    session_id = await _create_session(client, kb_id, headers)

    response = await client.post(
        f"/api/chat-sessions/{session_id}/ask",
        json={"question": "库里有什么？"},
        headers=headers,
    )
    assert response.status_code == 200

    events = _parse_sse(response.text)
    assert events[-1][0] == "sources"
    assert events[-1][1]["sources"] == []
    assert "（知识库未检索到与问题相关的内容）" in fake_llm["messages"][0]["content"]


@requires_db
async def test_llm_failure_emits_error_event_and_keeps_user_message(
    client: AsyncClient,
    test_user: dict,
    fixed_embeddings: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """大模型调用失败时先发 error 事件，助手消息不落库，用户消息保留。"""

    async def failing_stream(messages: list[dict[str, str]]):
        if False:  # pragma: no cover - 仅用于保持异步生成器语义
            yield ""
        raise BizException("大模型服务调用失败，请稍后重试")

    monkeypatch.setattr(chat_client, "stream_chat_completion", failing_stream)
    headers = test_user["headers"]
    kb_id = await _create_kb(client, headers, "失败路径库")
    await _seed_document_chunk(kb_id, "note.md", "一些参考资料", fixed_embeddings)
    session_id = await _create_session(client, kb_id, headers)

    response = await client.post(
        f"/api/chat-sessions/{session_id}/ask",
        json={"question": "会失败吗？"},
        headers=headers,
    )
    assert response.status_code == 200

    events = _parse_sse(response.text)
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["message"] == "大模型服务调用失败，请稍后重试"

    history = (
        await client.get(f"/api/chat-sessions/{session_id}/messages", headers=headers)
    ).json()["data"]
    assert [item["role"] for item in history] == ["user"]

    assert async_session_factory is not None
    async with async_session_factory() as session:
        assistant_count = len(
            (
                await session.execute(
                    select(ChatMessage).where(
                        ChatMessage.session_id == session_id,
                        ChatMessage.role == CHAT_ROLE_ASSISTANT,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert assistant_count == 0


@requires_db
async def test_cannot_ask_other_users_session(
    client: AsyncClient,
    test_user: dict,
) -> None:
    """越权访问他人会话返回 404 统一错误体。"""
    headers = test_user["headers"]
    kb_id = await _create_kb(client, headers, "越权会话库")
    session_id = await _create_session(client, kb_id, headers)

    assert async_session_factory is not None
    other_username = f"chat_test_{uuid.uuid4().hex[:12]}"
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
        response = await client.post(
            f"/api/chat-sessions/{session_id}/ask",
            json={"question": "越权提问"},
            headers=other_headers,
        )
        assert response.status_code == 404
        assert response.json()["code"] == 40400
    finally:
        async with async_session_factory() as session:
            await session.execute(delete(User).where(User.id == other_id))
            await session.commit()
