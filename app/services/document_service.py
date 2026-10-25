"""文档业务逻辑：上传保存、手动触发解析分块向量化、列表、分块查询、删除（级联）。

处理管线（用户手动触发后的后台任务）：
解析文本 → 按所选策略分块 → 批量 Embedding → 同事务写入分块向量并回写文档状态。
任何步骤失败都会把文档置为 failed 并记录原因；分块写入在事务内完成，
失败即回滚，不留脏分块/向量数据。
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.exceptions import BizException
from app.models.document import (
    DOCUMENT_STATUS_COMPLETED,
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_PENDING,
    DOCUMENT_STATUS_PROCESSING,
    Document,
)
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.services import embedding_client
from app.services.document_parser import DocumentParseError, parse_document_text
from app.services.knowledge_base_service import get_user_knowledge_base
from app.services.text_chunker import ChunkStrategy, chunk_text, resolve_chunk_strategy

logger = logging.getLogger(__name__)

ALLOWED_FILE_TYPES = {"pdf", "docx", "md", "txt"}
READ_BLOCK_SIZE = 1024 * 1024
MAX_ERROR_MESSAGE_LENGTH = 2000


def _max_upload_bytes() -> int:
    """单文件大小上限（字节），随配置动态计算便于测试覆盖。"""
    return settings.upload_max_mb * 1024 * 1024


async def save_uploaded_file(file: UploadFile) -> tuple[str, int, str]:
    """校验类型/大小并流式保存上传文件，返回 (存储路径, 文件大小, 文件类型)。"""
    original_name = Path(file.filename or "").name
    file_type = Path(original_name).suffix.lower().lstrip(".")
    if file_type not in ALLOWED_FILE_TYPES:
        raise BizException(
            f"不支持的文件类型：{file_type or '未知'}，仅支持 PDF/DOCX/MD/TXT",
            code=40001,
            http_status=400,
        )

    upload_root = Path(settings.upload_dir)
    try:
        upload_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.exception("上传目录创建失败：upload_dir=%s", upload_root)
        raise BizException("上传目录不可用，请检查 UPLOAD_DIR 配置") from exc

    target_path = upload_root / f"{uuid.uuid4().hex}.{file_type}"
    max_bytes = _max_upload_bytes()
    file_size = 0

    try:
        with target_path.open("wb") as output:
            while True:
                block = await file.read(READ_BLOCK_SIZE)
                if not block:
                    break
                file_size += len(block)
                if file_size > max_bytes:
                    raise BizException(
                        f"文件大小超过限制（最大 {settings.upload_max_mb}MB）",
                        code=40001,
                        http_status=400,
                    )
                output.write(block)
    except BizException:
        target_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        target_path.unlink(missing_ok=True)
        logger.exception("上传文件写入失败：target=%s", target_path)
        raise BizException("文件保存失败，请稍后重试") from exc

    if file_size == 0:
        target_path.unlink(missing_ok=True)
        raise BizException("文件内容为空", code=40001, http_status=400)

    logger.info(
        "上传文件已保存：filename=%s file_type=%s file_size=%s target=%s",
        original_name,
        file_type,
        file_size,
        target_path,
    )
    return str(target_path), file_size, file_type


async def create_document_from_upload(
    session: AsyncSession,
    user_id: int,
    kb_id: int,
    file: UploadFile,
) -> Document:
    """校验知识库归属并保存文件，写入待分块的文档记录（不自动触发分块）。"""
    kb = await get_user_knowledge_base(session, user_id, kb_id)
    filename = Path(file.filename or "").name
    file_path, file_size, file_type = await save_uploaded_file(file)

    document = Document(
        kb_id=kb.id,
        filename=filename,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        status=DOCUMENT_STATUS_PENDING,
    )
    session.add(document)
    try:
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        _remove_uploaded_file(file_path)
        logger.exception("文档记录写入失败：kb_id=%s filename=%s", kb.id, filename)
        raise BizException("文档记录创建失败，请稍后重试") from exc

    await session.refresh(document)
    logger.info(
        "文档已创建（处理中）：document_id=%s kb_id=%s filename=%s",
        document.id,
        kb.id,
        filename,
    )
    return document


async def list_documents(
    session: AsyncSession,
    user_id: int,
    kb_id: int,
) -> list[Document]:
    """列出知识库下文档（按上传时间倒序），先校验知识库归属。"""
    kb = await get_user_knowledge_base(session, user_id, kb_id)
    stmt = select(Document).where(Document.kb_id == kb.id).order_by(Document.id.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_user_document(
    session: AsyncSession,
    user_id: int,
    document_id: int,
) -> Document:
    """获取当前用户可访问的文档，不存在或越权时抛 404 业务异常。"""
    stmt = (
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(Document.id == document_id, KnowledgeBase.user_id == user_id)
    )
    document = (await session.execute(stmt)).scalar_one_or_none()
    if document is None:
        logger.info("文档不存在或无权访问：user_id=%s document_id=%s", user_id, document_id)
        raise BizException("文档不存在或无权访问", code=40400, http_status=404)
    return document


async def list_chunks(
    session: AsyncSession,
    user_id: int,
    document_id: int,
) -> list[DocumentChunk]:
    """按分块序号列出文档分块文本（用于前端分块抽屉）。"""
    document = await get_user_document(session, user_id, document_id)
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list((await session.execute(stmt)).scalars().all())


async def start_document_chunking(
    session: AsyncSession,
    user_id: int,
    document_id: int,
    chunk_strategy: str,
) -> Document:
    """校验策略与文档归属，将文档置为处理中，由路由调度后台分块任务。"""
    try:
        resolve_chunk_strategy(chunk_strategy)
    except ValueError as exc:
        logger.warning(
            "不支持的分块策略：document_id=%s strategy=%s", document_id, chunk_strategy
        )
        raise BizException(str(exc), code=40001, http_status=400) from exc

    document = await get_user_document(session, user_id, document_id)
    if document.status == DOCUMENT_STATUS_PROCESSING:
        raise BizException("文档正在分块中，请稍候", code=40001, http_status=400)

    document.status = DOCUMENT_STATUS_PROCESSING
    document.error_message = None
    document.chunk_count = 0
    try:
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.exception("文档分块状态更新失败：document_id=%s", document_id)
        raise BizException("启动分块失败，请稍后重试") from exc

    await session.refresh(document)
    logger.info("文档开始分块：document_id=%s strategy=%s", document_id, chunk_strategy)
    return document


async def delete_document(
    session: AsyncSession,
    user_id: int,
    document_id: int,
) -> None:
    """删除文档（数据库级联删除分块与向量），提交后清理磁盘文件。"""
    document = await get_user_document(session, user_id, document_id)
    file_path = document.file_path
    await session.delete(document)
    await session.commit()
    _remove_uploaded_file(file_path)
    logger.info("文档已删除：document_id=%s kb_id=%s", document_id, document.kb_id)


async def process_document(
    document_id: int,
    chunk_strategy: str = ChunkStrategy.PARAGRAPH.value,
) -> None:
    """后台任务：按指定策略解析、分块、向量化并回写文档状态；失败时回写原因且不留脏分块。"""
    if async_session_factory is None:
        logger.warning("数据库未初始化，跳过文档处理：document_id=%s", document_id)
        return

    async with async_session_factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            logger.warning("文档已不存在，跳过处理：document_id=%s", document_id)
            return
        file_path = document.file_path
        file_type = document.file_type
        kb_id = document.kb_id
        filename = document.filename

    try:
        # 解析与分块为同步阻塞操作，放到线程执行避免阻塞事件循环
        text = await asyncio.to_thread(parse_document_text, file_path, file_type)
        chunks = await asyncio.to_thread(chunk_text, text, strategy=chunk_strategy)
        if not chunks:
            raise DocumentParseError("文档未解析出有效文本")
        vectors = await embedding_client.embed_texts(chunks)
    except Exception as exc:  # noqa: BLE001 - 后台任务需兜底全部失败并回写状态
        logger.exception(
            "文档处理失败：document_id=%s filename=%s file_type=%s file_path=%s error_type=%s",
            document_id,
            filename,
            file_type,
            file_path,
            type(exc).__name__,
        )
        await _mark_document_failed(document_id, _failure_message(exc))
        return

    await _store_chunks(document_id, kb_id, chunks, vectors)


def _failure_message(exc: Exception) -> str:
    """把处理异常转为可展示的失败原因（内部细节只记日志）。"""
    if isinstance(exc, (BizException, DocumentParseError)):
        return exc.message if isinstance(exc, BizException) else str(exc)
    return "文档处理失败，请检查文件是否损坏；详情见服务端日志"


async def _store_chunks(
    document_id: int,
    kb_id: int,
    chunks: list[str],
    vectors: list[list[float]],
) -> None:
    """同事务写入全部分块向量并置文档为完成；失败回滚并标记失败。"""
    if async_session_factory is None:
        return

    async with async_session_factory() as session:
        try:
            document = await session.get(Document, document_id)
            if document is None:
                logger.warning("文档已不存在，跳过分块写入：document_id=%s", document_id)
                return

            # 幂等保护：清理历史分块，避免重复处理产生脏数据
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
            session.add_all(
                [
                    DocumentChunk(
                        kb_id=kb_id,
                        document_id=document_id,
                        chunk_index=index,
                        content=content,
                        embedding=vector,
                    )
                    for index, (content, vector) in enumerate(zip(chunks, vectors, strict=True))
                ]
            )
            document.status = DOCUMENT_STATUS_COMPLETED
            document.chunk_count = len(chunks)
            document.error_message = None
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - 写入失败必须回滚并回写失败状态
            await session.rollback()
            logger.exception(
                "文档分块写入失败：document_id=%s chunk_count=%s error_type=%s",
                document_id,
                len(chunks),
                type(exc).__name__,
            )
            await _mark_document_failed(document_id, "分块向量写入失败，请稍后重试")
            return

    logger.info("文档处理完成：document_id=%s chunk_count=%s", document_id, len(chunks))


async def _mark_document_failed(document_id: int, message: str) -> None:
    """回写失败状态与原因，并清理历史分块（重新分块失败时不留旧数据）。"""
    if async_session_factory is None:
        return

    async with async_session_factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        document.status = DOCUMENT_STATUS_FAILED
        document.error_message = message[:MAX_ERROR_MESSAGE_LENGTH]
        document.chunk_count = 0
        try:
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            logger.exception("文档失败状态回写失败：document_id=%s", document_id)


def _remove_uploaded_file(file_path: str) -> None:
    """删除上传目录内的文件；路径越界或删除失败仅记录日志，不影响主流程。"""
    path = Path(file_path)
    try:
        upload_root = Path(settings.upload_dir).resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(upload_root):
            logger.warning("拒绝删除上传目录之外的文件：path=%s upload_dir=%s", file_path, upload_root)
            return
        resolved.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("删除上传文件失败：path=%s detail=%s", file_path, exc)
