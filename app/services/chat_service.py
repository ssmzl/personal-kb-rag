"""问答会话业务逻辑与 RAG 检索。

- 会话：新建 / 重命名 / 删除 / 列表 / 历史消息；
- 检索：问题向量 → pgvector 余弦距离 TopK（按 kb_id 过滤）；
- 问答：拼接 system prompt（强制仅依据资料回答）与近 6 轮历史后调用大模型，
  以事件流形式产出 ``delta`` 增量文本，结束后产出 ``sources`` 引用来源；
  失败统一产出 ``error`` 事件，保证流不中断。
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.exceptions import BizException
from app.models.chat_message import CHAT_ROLE_ASSISTANT, CHAT_ROLE_USER, ChatMessage
from app.models.chat_session import ChatSession
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.services import chat_client, embedding_client
from app.services.knowledge_base_service import get_user_knowledge_base

logger = logging.getLogger(__name__)

RETRIEVAL_TOP_K = 5
HISTORY_ROUNDS = 6
HISTORY_MESSAGE_LIMIT = HISTORY_ROUNDS * 2
DEFAULT_SESSION_TITLE = "新对话"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

SYSTEM_PROMPT = """你是个人知识库问答助手。请严格依据下面提供的「参考资料」回答用户问题：
1. 只能使用参考资料中的信息作答，不得编造，也不得使用参考资料之外的知识；
2. 如果参考资料无法回答该问题，请明确回答「知识库中未找到相关内容」，并简要说明资料中缺少哪方面信息；
3. 使用简体中文回答，条理清晰；引用资料时标注资料编号与文档名。"""


@dataclass(frozen=True)
class RetrievedChunk:
    """检索命中的分块及其来源信息。"""

    document_id: int
    document_name: str
    chunk_index: int
    content: str

    def to_source(self) -> dict[str, Any]:
        """转为引用来源输出结构（文档名 + 片段）。"""
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "chunk_index": self.chunk_index,
            "content": self.content,
        }


# ---------- 会话管理 ----------


async def list_sessions(
    session: AsyncSession,
    user_id: int,
    kb_id: int,
) -> list[ChatSession]:
    """列出知识库下全部会话，按 ID 倒序（最近创建的在前）。"""
    kb = await get_user_knowledge_base(session, user_id, kb_id)
    stmt = select(ChatSession).where(ChatSession.kb_id == kb.id).order_by(ChatSession.id.desc())
    return list((await session.execute(stmt)).scalars().all())


async def create_session(
    session: AsyncSession,
    user_id: int,
    kb_id: int,
    title: str | None,
) -> ChatSession:
    """在指定知识库下新建会话，标题缺省为「新对话」。"""
    kb = await get_user_knowledge_base(session, user_id, kb_id)
    clean_title = (title or "").strip() or DEFAULT_SESSION_TITLE

    chat_session = ChatSession(kb_id=kb.id, title=clean_title)
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    logger.info(
        "会话已创建：user_id=%s kb_id=%s session_id=%s title=%s",
        user_id,
        kb.id,
        chat_session.id,
        clean_title,
    )
    return chat_session


async def get_user_session(
    session: AsyncSession,
    user_id: int,
    session_id: int,
) -> ChatSession:
    """按 ID 获取当前用户可访问的会话，不存在或越权时抛 404 业务异常。"""
    stmt = (
        select(ChatSession)
        .join(KnowledgeBase, KnowledgeBase.id == ChatSession.kb_id)
        .where(ChatSession.id == session_id, KnowledgeBase.user_id == user_id)
    )
    chat_session = (await session.execute(stmt)).scalar_one_or_none()
    if chat_session is None:
        logger.info("会话不存在或无权访问：user_id=%s session_id=%s", user_id, session_id)
        raise BizException("会话不存在或无权访问", code=40400, http_status=404)
    return chat_session


async def rename_session(
    session: AsyncSession,
    user_id: int,
    session_id: int,
    title: str,
) -> ChatSession:
    """重命名会话并返回更新后的实体。"""
    chat_session = await get_user_session(session, user_id, session_id)
    chat_session.title = title
    await session.commit()
    await session.refresh(chat_session)
    logger.info("会话已重命名：user_id=%s session_id=%s title=%s", user_id, session_id, title)
    return chat_session


async def delete_session(
    session: AsyncSession,
    user_id: int,
    session_id: int,
) -> None:
    """删除会话，其下消息随 ON DELETE CASCADE 一并清除。"""
    chat_session = await get_user_session(session, user_id, session_id)
    await session.delete(chat_session)
    await session.commit()
    logger.info("会话已删除：user_id=%s session_id=%s", user_id, session_id)


async def list_messages(
    session: AsyncSession,
    user_id: int,
    session_id: int,
) -> list[ChatMessage]:
    """按时间顺序列出会话历史消息。"""
    chat_session = await get_user_session(session, user_id, session_id)
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def load_history(
    session: AsyncSession,
    session_id: int,
    limit: int = HISTORY_MESSAGE_LIMIT,
) -> list[ChatMessage]:
    """加载最近 ``HISTORY_ROUNDS`` 轮历史（按时间正序）。"""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    messages = list((await session.execute(stmt)).scalars().all())
    messages.reverse()
    return messages


# ---------- 检索与提示词 ----------


async def retrieve_chunks(
    session: AsyncSession,
    kb_id: int,
    question: str,
    top_k: int = RETRIEVAL_TOP_K,
) -> list[RetrievedChunk]:
    """问题向量化后在指定知识库内按余弦距离检索 TopK 分块。"""
    vectors = await embedding_client.embed_texts([question])
    if not vectors:
        raise BizException("Embedding 服务未返回向量，请稍后重试")

    distance = DocumentChunk.embedding.cosine_distance(vectors[0])
    stmt = (
        select(DocumentChunk, Document.filename, distance.label("distance"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.kb_id == kb_id)
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await session.execute(stmt)).all()
    chunks = [
        RetrievedChunk(
            document_id=chunk.document_id,
            document_name=filename,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
        )
        for chunk, filename, _distance in rows
    ]
    logger.info("向量检索完成：kb_id=%s top_k=%s hits=%s", kb_id, top_k, len(chunks))
    return chunks


def build_system_prompt(chunks: list[RetrievedChunk]) -> str:
    """拼接强制「仅依据资料回答」的 system prompt 与参考资料。"""
    if not chunks:
        reference = "（知识库未检索到与问题相关的内容）"
    else:
        reference = "\n\n".join(
            f"【资料 {index}】文档：{chunk.document_name}（片段 {chunk.chunk_index + 1}）\n"
            f"{chunk.content}"
            for index, chunk in enumerate(chunks, start=1)
        )
    return f"{SYSTEM_PROMPT}\n\n【参考资料】\n{reference}"


def build_chat_messages(
    history: list[ChatMessage],
    question: str,
    chunks: list[RetrievedChunk],
) -> list[dict[str, str]]:
    """构造对话消息：system（含参考资料）+ 近 6 轮历史 + 当前问题。"""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(chunks)}
    ]
    messages.extend({"role": message.role, "content": message.content} for message in history)
    messages.append({"role": CHAT_ROLE_USER, "content": question})
    return messages


# ---------- 流式问答 ----------


async def stream_answer_events(
    user_id: int,
    session_id: int,
    kb_id: int,
    question: str,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """产出问答事件：``delta``（增量文本）→ ``sources``（引用来源）；失败产出 ``error``。"""
    if async_session_factory is None:
        yield "error", {"message": "数据库未初始化，请检查 DATABASE_URL 配置"}
        return

    async with async_session_factory() as session:
        try:
            chunks = await retrieve_chunks(session, kb_id, question)
            history = await load_history(session, session_id)
        except BizException as exc:
            logger.warning(
                "问答检索失败：user_id=%s session_id=%s kb_id=%s message=%s",
                user_id,
                session_id,
                kb_id,
                exc.message,
            )
            yield "error", {"message": exc.message}
            return
        except Exception:
            logger.exception(
                "问答检索异常：user_id=%s session_id=%s kb_id=%s",
                user_id,
                session_id,
                kb_id,
            )
            yield "error", {"message": "知识库检索失败，请稍后重试"}
            return

        try:
            session.add(ChatMessage(session_id=session_id, role=CHAT_ROLE_USER, content=question))
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            logger.exception("用户消息保存失败：session_id=%s", session_id)
            yield "error", {"message": "消息保存失败，请稍后重试"}
            return

        messages = build_chat_messages(history, question, chunks)
        answer_parts: list[str] = []
        try:
            async for delta in chat_client.stream_chat_completion(messages):
                answer_parts.append(delta)
                yield "delta", {"content": delta}
        except asyncio.CancelledError:
            logger.info("客户端断开，问答流式输出中止：user_id=%s session_id=%s", user_id, session_id)
            raise
        except BizException as exc:
            logger.warning(
                "大模型流式输出失败：user_id=%s session_id=%s message=%s",
                user_id,
                session_id,
                exc.message,
            )
            yield "error", {"message": exc.message}
            return
        except Exception:
            logger.exception("大模型流式输出异常：user_id=%s session_id=%s", user_id, session_id)
            yield "error", {"message": "问答服务异常，请稍后重试"}
            return

        answer = "".join(answer_parts)
        if not answer:
            logger.warning("大模型未返回内容：user_id=%s session_id=%s", user_id, session_id)
            yield "error", {"message": "大模型未返回内容，请稍后重试"}
            return

        sources = [chunk.to_source() for chunk in chunks]
        assistant_message = ChatMessage(
            session_id=session_id,
            role=CHAT_ROLE_ASSISTANT,
            content=answer,
            sources=sources,
        )
        try:
            session.add(assistant_message)
            await session.commit()
            await session.refresh(assistant_message)
        except SQLAlchemyError:
            await session.rollback()
            logger.exception(
                "回答消息保存失败：session_id=%s answer_length=%s",
                session_id,
                len(answer),
            )
            yield "error", {"message": "回答已生成但保存失败，请稍后重试"}
            return

        logger.info(
            "问答完成：user_id=%s session_id=%s kb_id=%s answer_length=%s source_count=%s",
            user_id,
            session_id,
            kb_id,
            len(answer),
            len(sources),
        )
        yield "sources", {
            "sources": sources,
            "assistant_message_id": assistant_message.id,
            "create_time": assistant_message.create_time.strftime(TIME_FORMAT),
        }
