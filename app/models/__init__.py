"""SQLAlchemy ORM 模型。

导入本模块即可将全部模型注册到 ``Base.metadata``。
"""

from app.models.base import TimestampMixin
from app.models.chat_message import (
    CHAT_ROLE_ASSISTANT,
    CHAT_ROLE_USER,
    ChatMessage,
)
from app.models.chat_session import ChatSession
from app.models.document import (
    DOCUMENT_STATUS_COMPLETED,
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_PROCESSING,
    Document,
)
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User

__all__ = [
    "CHAT_ROLE_ASSISTANT",
    "CHAT_ROLE_USER",
    "DOCUMENT_STATUS_COMPLETED",
    "DOCUMENT_STATUS_FAILED",
    "DOCUMENT_STATUS_PROCESSING",
    "ChatMessage",
    "ChatSession",
    "Document",
    "DocumentChunk",
    "KnowledgeBase",
    "TimestampMixin",
    "User",
]
