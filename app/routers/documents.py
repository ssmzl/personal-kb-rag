"""文档路由：上传、手动触发分块（异步向量化）、列表、分块查询、删除（级联删分块）。"""

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.schemas.common import ApiResponse, ok
from app.schemas.document import DocumentChunkItem, DocumentChunkRequest, DocumentItem
from app.services import document_service

router = APIRouter(tags=["documents"])


def _to_item(document: Document) -> DocumentItem:
    """ORM 实体转文档列表项。"""
    return DocumentItem(
        id=document.id,
        kb_id=document.kb_id,
        filename=document.filename,
        file_type=document.file_type,
        file_size=document.file_size,
        status=document.status,
        error_message=document.error_message,
        chunk_count=document.chunk_count,
        create_time=document.create_time,
        update_time=document.update_time,
    )


def _to_chunk_item(chunk: DocumentChunk) -> DocumentChunkItem:
    """ORM 实体转分块项（不返回向量）。"""
    return DocumentChunkItem(
        id=chunk.id,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        create_time=chunk.create_time,
    )


@router.get(
    "/knowledge-bases/{kb_id}/documents",
    response_model=ApiResponse[list[DocumentItem]],
    summary="文档列表",
)
async def list_documents(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[DocumentItem]]:
    """列出知识库下的文档及处理状态。"""
    documents = await document_service.list_documents(session, current_user.id, kb_id)
    return ok([_to_item(document) for document in documents])


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=ApiResponse[DocumentItem],
    summary="上传文档",
)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(..., description="PDF/DOCX/MD/TXT 文件，单文件不超过 20MB"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[DocumentItem]:
    """保存文件并写入待分块的文档记录，不自动触发解析与向量化。"""
    document = await document_service.create_document_from_upload(
        session, current_user.id, kb_id, file
    )
    return ok(_to_item(document), message="上传成功，请选择策略开始分块")


@router.post(
    "/documents/{document_id}/chunk",
    response_model=ApiResponse[DocumentItem],
    summary="开始/重新分块",
)
async def chunk_document(
    document_id: int,
    payload: DocumentChunkRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[DocumentItem]:
    """按指定策略异步解析、分块并向量化，支持对已完成文档重新分块。"""
    document = await document_service.start_document_chunking(
        session, current_user.id, document_id, payload.chunk_strategy
    )
    background_tasks.add_task(
        document_service.process_document, document.id, payload.chunk_strategy
    )
    return ok(_to_item(document), message="已开始分块")


@router.get(
    "/documents/{document_id}/chunks",
    response_model=ApiResponse[list[DocumentChunkItem]],
    summary="文档分块列表",
)
async def list_document_chunks(
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[DocumentChunkItem]]:
    """查看文档的全部分块文本。"""
    chunks = await document_service.list_chunks(session, current_user.id, document_id)
    return ok([_to_chunk_item(chunk) for chunk in chunks])


@router.delete(
    "/documents/{document_id}",
    response_model=ApiResponse[None],
    summary="删除文档",
)
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """删除文档，级联清除其分块与向量记录，并清理磁盘文件。"""
    await document_service.delete_document(session, current_user.id, document_id)
    return ok(message="删除成功")
