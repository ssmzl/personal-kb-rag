"""知识库管理路由：创建、重命名、删除、列表。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.common import ApiResponse, ok
from app.schemas.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseItem,
    KnowledgeBaseRenameRequest,
)
from app.services import knowledge_base_service

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _to_item(kb: KnowledgeBase, document_count: int) -> KnowledgeBaseItem:
    """ORM 实体转列表项。"""
    return KnowledgeBaseItem(
        id=kb.id,
        name=kb.name,
        document_count=document_count,
        create_time=kb.create_time,
        update_time=kb.update_time,
    )


@router.get("", response_model=ApiResponse[list[KnowledgeBaseItem]], summary="知识库列表")
async def list_knowledge_bases(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[KnowledgeBaseItem]]:
    """列出当前用户的知识库，含各库文档数。"""
    items = await knowledge_base_service.list_knowledge_bases(session, current_user.id)
    return ok([_to_item(kb, document_count) for kb, document_count in items])


@router.post("", response_model=ApiResponse[KnowledgeBaseItem], summary="创建知识库")
async def create_knowledge_base(
    body: KnowledgeBaseCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[KnowledgeBaseItem]:
    """创建知识库，新库文档数为 0。"""
    kb = await knowledge_base_service.create_knowledge_base(session, current_user.id, body.name)
    return ok(_to_item(kb, document_count=0), message="创建成功")


@router.put("/{kb_id}", response_model=ApiResponse[KnowledgeBaseItem], summary="重命名知识库")
async def rename_knowledge_base(
    kb_id: int,
    body: KnowledgeBaseRenameRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[KnowledgeBaseItem]:
    """重命名知识库，返回更新后的列表项。"""
    kb = await knowledge_base_service.rename_knowledge_base(
        session, current_user.id, kb_id, body.name
    )
    document_count = await knowledge_base_service.count_documents(session, kb.id)
    return ok(_to_item(kb, document_count), message="重命名成功")


@router.delete("/{kb_id}", response_model=ApiResponse[None], summary="删除知识库")
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """删除知识库，级联清除其下文档、分块与向量记录。"""
    await knowledge_base_service.delete_knowledge_base(session, current_user.id, kb_id)
    return ok(message="删除成功")
