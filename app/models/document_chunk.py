"""文档分块与向量模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.knowledge_base import KnowledgeBase


class DocumentChunk(Base, TimestampMixin):
    """文档分块，embedding 为 1024 维向量（余弦距离检索）。"""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimension),
        nullable=False,
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship()
    document: Mapped[Document] = relationship(back_populates="chunks")
