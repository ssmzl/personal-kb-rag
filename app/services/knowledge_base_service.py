"""知识库业务逻辑：创建、重命名、删除（级联）、列表（含文档数聚合）。

所有操作按归属用户隔离；删除走数据库 ON DELETE CASCADE，在同事务内
级联清除文档与分块向量记录。
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BizException
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


async def create_knowledge_base(
    session: AsyncSession,
    user_id: int,
    name: str,
) -> KnowledgeBase:
    """创建知识库并返回。"""
    kb = KnowledgeBase(user_id=user_id, name=name)
    session.add(kb)
    await session.commit()
    await session.refresh(kb)
    logger.info("知识库已创建：user_id=%s kb_id=%s name=%s", user_id, kb.id, name)
    return kb


async def get_user_knowledge_base(
    session: AsyncSession,
    user_id: int,
    kb_id: int,
) -> KnowledgeBase:
    """按 ID 获取当前用户的知识库，不存在或不属于该用户时抛 404 业务异常。"""
    stmt = select(KnowledgeBase).where(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.user_id == user_id,
    )
    kb = (await session.execute(stmt)).scalar_one_or_none()
    if kb is None:
        logger.info("知识库不存在或无权访问：user_id=%s kb_id=%s", user_id, kb_id)
        raise BizException("知识库不存在或无权访问", code=40400, http_status=404)
    return kb


async def rename_knowledge_base(
    session: AsyncSession,
    user_id: int,
    kb_id: int,
    name: str,
) -> KnowledgeBase:
    """重命名知识库并返回更新后的实体。"""
    kb = await get_user_knowledge_base(session, user_id, kb_id)
    kb.name = name
    await session.commit()
    await session.refresh(kb)
    logger.info("知识库已重命名：user_id=%s kb_id=%s name=%s", user_id, kb_id, name)
    return kb


async def delete_knowledge_base(
    session: AsyncSession,
    user_id: int,
    kb_id: int,
) -> None:
    """删除知识库，同事务内级联删除其下文档与分块向量（DB ON DELETE CASCADE）。"""
    kb = await get_user_knowledge_base(session, user_id, kb_id)
    await session.delete(kb)
    await session.commit()
    logger.info("知识库已删除（含级联文档与分块）：user_id=%s kb_id=%s", user_id, kb_id)


async def count_documents(session: AsyncSession, kb_id: int) -> int:
    """统计知识库下文档数。"""
    stmt = select(func.count(Document.id)).where(Document.kb_id == kb_id)
    return (await session.execute(stmt)).scalar_one()


async def list_knowledge_bases(
    session: AsyncSession,
    user_id: int,
) -> list[tuple[KnowledgeBase, int]]:
    """列出当前用户全部知识库，聚合并返回各库文档数，按 ID 升序。"""
    stmt = (
        select(KnowledgeBase, func.count(Document.id))
        .outerjoin(Document, Document.kb_id == KnowledgeBase.id)
        .where(KnowledgeBase.user_id == user_id)
        .group_by(KnowledgeBase.id)
        .order_by(KnowledgeBase.id)
    )
    rows = (await session.execute(stmt)).all()
    return [(kb, document_count) for kb, document_count in rows]
