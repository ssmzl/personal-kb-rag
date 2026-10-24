"""数据库模型与真实库向量读写测试。

真实库测试需要配置 ``DATABASE_URL``（可先 ``docker compose up -d postgres``），
未配置时自动跳过，避免影响不依赖数据库的单元测试。
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.database import Base, async_session_factory, engine, init_database
from app.models import Document, DocumentChunk, KnowledgeBase, User
from app.models.document import DOCUMENT_STATUS_COMPLETED

EXPECTED_TABLES = {
    "users",
    "knowledge_bases",
    "documents",
    "document_chunks",
    "chat_sessions",
    "chat_messages",
}


def test_models_register_all_tables() -> None:
    """六张表全部注册到 ORM metadata，embedding 列为 vector(1024)。"""
    assert EXPECTED_TABLES.issubset(Base.metadata.tables)

    embedding_type = DocumentChunk.__table__.c.embedding.type
    assert embedding_type.dim == settings.embedding_dimension == 1024


@pytest.mark.skipif(not settings.database_url, reason="未配置 DATABASE_URL，跳过真实库测试")
async def test_init_database_and_vector_search() -> None:
    """建库脚本可重复执行；向量写入后可按余弦距离检索回最近分块。"""
    await init_database()
    await init_database()  # 幂等：重复执行不应报错

    assert async_session_factory is not None
    async with async_session_factory() as session:
        user = User(username=f"test_{uuid.uuid4().hex[:12]}", password_hash="test-hash")
        session.add(user)
        await session.flush()

        kb = KnowledgeBase(user_id=user.id, name="测试知识库")
        session.add(kb)
        await session.flush()

        document = Document(
            kb_id=kb.id,
            filename="测试文档.txt",
            file_path="uploads/test.txt",
            file_type="txt",
            file_size=128,
            status=DOCUMENT_STATUS_COMPLETED,
            chunk_count=3,
        )
        session.add(document)
        await session.flush()

        vectors = [
            [0.0] * settings.embedding_dimension,
            [1.0] + [0.0] * (settings.embedding_dimension - 1),
            [0.0, 1.0] + [0.0] * (settings.embedding_dimension - 2),
        ]
        session.add_all(
            [
                DocumentChunk(
                    kb_id=kb.id,
                    document_id=document.id,
                    chunk_index=index,
                    content=f"分块内容 {index}",
                    embedding=vector,
                )
                for index, vector in enumerate(vectors)
            ]
        )
        await session.commit()

        try:
            query_vector = [1.0] + [0.0] * (settings.embedding_dimension - 1)
            stmt = (
                select(DocumentChunk)
                .where(DocumentChunk.kb_id == kb.id)
                .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
                .limit(1)
            )
            closest = (await session.execute(stmt)).scalar_one()
            assert closest.chunk_index == 1
            assert closest.document_id == document.id
        finally:
            # 级联删除知识库（文档、分块随之删除），再清理测试用户
            await session.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()

    # 每个 async 测试运行在独立事件循环，释放连接池避免跨循环复用残留连接
    if engine is not None:
        await engine.dispose()
