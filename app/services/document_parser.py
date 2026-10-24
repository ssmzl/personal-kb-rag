"""文档解析：PDF(pypdf) / DOCX(python-docx) / MD、TXT 纯文本，统一输出纯文本。

解析为同步阻塞操作，调用方应放到线程中执行（见 ``document_service``）。
"""

import logging
from pathlib import Path
from zipfile import BadZipFile

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

PLAIN_TEXT_TYPES = {"md", "txt"}
SUPPORTED_TYPES = PLAIN_TEXT_TYPES | {"pdf", "docx"}

# 纯文本按常见编码依次尝试（UTF-8 带 BOM / 无 BOM → 中文 GB18030）
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")


class DocumentParseError(Exception):
    """文档解析失败（文件损坏、编码无法识别、未解析出文本等）。"""


def parse_document_text(file_path: str | Path, file_type: str) -> str:
    """按文件类型解析出纯文本，失败抛 ``DocumentParseError``。"""
    path = Path(file_path)
    normalized_type = file_type.lower()
    if normalized_type not in SUPPORTED_TYPES:
        raise DocumentParseError(f"不支持的文件类型：{file_type}")

    if not path.is_file():
        raise DocumentParseError(f"文件不存在：{path}")

    if normalized_type == "pdf":
        text = _parse_pdf(path)
    elif normalized_type == "docx":
        text = _parse_docx(path)
    else:
        text = _parse_plain_text(path)

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise DocumentParseError("文档未解析出有效文本")
    return normalized


def _parse_pdf(path: Path) -> str:
    """提取 PDF 全部页面文本，按页以空行拼接。"""
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise DocumentParseError("PDF 已加密，无法解析")
        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    except DocumentParseError:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        logger.warning("PDF 解析失败：path=%s error_type=%s detail=%s", path, type(exc).__name__, exc)
        raise DocumentParseError(f"PDF 解析失败：{type(exc).__name__}") from exc

    return "\n\n".join(page_text for page_text in page_texts if page_text)


def _parse_docx(path: Path) -> str:
    """提取 DOCX 全部段落文本（空段落跳过）。"""
    try:
        document = DocxDocument(str(path))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    except (PackageNotFoundError, BadZipFile, OSError, ValueError, KeyError) as exc:
        logger.warning(
            "DOCX 解析失败：path=%s error_type=%s detail=%s",
            path,
            type(exc).__name__,
            exc,
        )
        raise DocumentParseError(f"DOCX 解析失败：{type(exc).__name__}") from exc

    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _parse_plain_text(path: Path) -> str:
    """按候选编码解码纯文本文件。"""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        logger.warning("读取文本文件失败：path=%s detail=%s", path, exc)
        raise DocumentParseError("读取文件失败") from exc

    for encoding in TEXT_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            logger.debug("文本编码不匹配，尝试下一编码：path=%s encoding=%s", path, encoding)

    raise DocumentParseError("文本文件编码无法识别，请使用 UTF-8 或 GB18030 编码")
