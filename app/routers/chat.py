"""问答会话路由：会话增删改查、历史消息、SSE 流式问答。

SSE 输出约定：
- ``event: delta``   data: ``{"content": "增量文本"}``
- ``event: sources`` data: ``{"sources": [...], "assistant_message_id": ..., "create_time": ...}``
- ``event: error``   data: ``{"message": "错误提示"}``（先发 error 再结束流）
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.user import User
from app.schemas.chat import (
    ChatAskRequest,
    ChatMessageItem,
    ChatSessionCreateRequest,
    ChatSessionItem,
    ChatSessionRenameRequest,
    ChatSourceItem,
)
from app.schemas.common import ApiResponse, ok
from app.services import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _to_session_item(chat_session: ChatSession) -> ChatSessionItem:
    """ORM 实体转会话列表项。"""
    return ChatSessionItem(
        id=chat_session.id,
        kb_id=chat_session.kb_id,
        title=chat_session.title,
        create_time=chat_session.create_time,
        update_time=chat_session.update_time,
    )


def _to_message_item(message: ChatMessage) -> ChatMessageItem:
    """ORM 实体转消息项，引用来源还原为结构化对象。"""
    sources = (
        [ChatSourceItem.model_validate(source) for source in message.sources]
        if message.sources
        else None
    )
    return ChatMessageItem(
        id=message.id,
        role=message.role,
        content=message.content,
        sources=sources,
        create_time=message.create_time,
    )


def _format_sse(event: str, data: dict[str, Any]) -> str:
    """按 SSE 协议格式化单个事件。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _sse_stream(
    user_id: int,
    session_id: int,
    kb_id: int,
    question: str,
) -> AsyncIterator[str]:
    """把业务事件流包装为 SSE；未捕获异常兜底发送 error 事件，保证前端不静默。"""
    try:
        async for event, data in chat_service.stream_answer_events(
            user_id, session_id, kb_id, question
        ):
            yield _format_sse(event, data)
    except asyncio.CancelledError:
        logger.info("客户端断开，SSE 流结束：user_id=%s session_id=%s", user_id, session_id)
        raise
    except Exception:
        logger.exception("SSE 问答未捕获异常：user_id=%s session_id=%s", user_id, session_id)
        yield _format_sse("error", {"message": "问答服务异常，请稍后重试"})


@router.get(
    "/knowledge-bases/{kb_id}/chat-sessions",
    response_model=ApiResponse[list[ChatSessionItem]],
    summary="会话列表",
)
async def list_sessions(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ChatSessionItem]]:
    """列出知识库下的全部会话。"""
    sessions = await chat_service.list_sessions(session, current_user.id, kb_id)
    return ok([_to_session_item(item) for item in sessions])


@router.post(
    "/knowledge-bases/{kb_id}/chat-sessions",
    response_model=ApiResponse[ChatSessionItem],
    summary="新建会话",
)
async def create_session(
    kb_id: int,
    body: ChatSessionCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ChatSessionItem]:
    """新建会话，标题缺省为「新对话」。"""
    chat_session = await chat_service.create_session(
        session, current_user.id, kb_id, body.title
    )
    return ok(_to_session_item(chat_session), message="创建成功")


@router.put(
    "/chat-sessions/{session_id}",
    response_model=ApiResponse[ChatSessionItem],
    summary="重命名会话",
)
async def rename_session(
    session_id: int,
    body: ChatSessionRenameRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ChatSessionItem]:
    """重命名会话。"""
    chat_session = await chat_service.rename_session(
        session, current_user.id, session_id, body.title
    )
    return ok(_to_session_item(chat_session), message="重命名成功")


@router.delete(
    "/chat-sessions/{session_id}",
    response_model=ApiResponse[None],
    summary="删除会话",
)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """删除会话，其下消息一并清除。"""
    await chat_service.delete_session(session, current_user.id, session_id)
    return ok(message="删除成功")


@router.get(
    "/chat-sessions/{session_id}/messages",
    response_model=ApiResponse[list[ChatMessageItem]],
    summary="会话历史消息",
)
async def list_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ChatMessageItem]]:
    """按时间顺序加载会话历史消息。"""
    messages = await chat_service.list_messages(session, current_user.id, session_id)
    return ok([_to_message_item(message) for message in messages])


@router.post("/chat-sessions/{session_id}/ask", summary="流式问答（SSE）")
async def ask(
    session_id: int,
    body: ChatAskRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """基于知识库检索并以 SSE 流式返回回答，流结束后附带引用来源。"""
    chat_session = await chat_service.get_user_session(session, current_user.id, session_id)
    kb_id = chat_session.kb_id
    # 结束本次只读查询事务，避免流式输出期间一直占用连接池连接
    await session.commit()

    return StreamingResponse(
        _sse_stream(current_user.id, session_id, kb_id, body.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
