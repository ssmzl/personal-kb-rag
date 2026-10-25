"""文本分块器：支持多种分块策略（段落 / 固定窗口 / 句子 / Markdown 标题）。

参考常见 RAG 分块实践，不同结构的文档适用不同切分方式：
1. paragraph（默认）：段落优先，短段落尽量合并，超长段落按窗口切分；
2. fixed：固定窗口滑动切分，忽略段落与句子边界，适合无结构文本；
3. sentence：按句子边界聚合，尽量保证句子完整，适合说明文、问答；
4. markdown：按 Markdown 标题切分小节，超长小节再按段落切分，无标题时退化为段落策略。

所有策略都保证分块长度不超过 ``chunk_size``（单段/单句本身超长时按窗口切分），
并支持相邻块重叠 ``overlap`` 个字符。
"""

import re
from enum import Enum

DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50

# 空行（含仅空白行）分隔段落
_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n")
# 中英文句末标点后切分，同时兼容按行切分
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?；;…])\s*|\n+")
# Markdown 1~6 级标题作为小节边界
_MARKDOWN_HEADING_PATTERN = re.compile(r"^#{1,6}\s", re.MULTILINE)
_MARKDOWN_HEADING_SPLIT_PATTERN = re.compile(r"(?=^#{1,6}\s)", re.MULTILINE)


class ChunkStrategy(str, Enum):
    """分块策略枚举，值即前后端契约中的策略标识。"""

    PARAGRAPH = "paragraph"
    FIXED = "fixed"
    SENTENCE = "sentence"
    MARKDOWN = "markdown"


def resolve_chunk_strategy(strategy: ChunkStrategy | str) -> ChunkStrategy:
    """将策略标识转为枚举，非法值抛出 ValueError。"""
    if isinstance(strategy, ChunkStrategy):
        return strategy
    try:
        return ChunkStrategy(strategy)
    except ValueError as exc:
        options = "、".join(item.value for item in ChunkStrategy)
        raise ValueError(f"不支持的分块策略：{strategy}，可选值：{options}") from exc


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    strategy: ChunkStrategy | str = ChunkStrategy.PARAGRAPH,
) -> list[str]:
    """按指定策略将纯文本切分为带重叠的分块列表，空文本返回空列表。

    :param text: 待切分文本
    :param chunk_size: 单块最大字符数
    :param overlap: 相邻块重叠字符数，需小于 chunk_size
    :param strategy: 分块策略，见 ``ChunkStrategy``
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size 必须为正整数，当前值：{chunk_size}")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(f"overlap 必须满足 0 <= overlap < chunk_size，当前值：{overlap}")

    resolved = resolve_chunk_strategy(strategy)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    if resolved is ChunkStrategy.FIXED:
        return _fixed_window_chunks(normalized, chunk_size, overlap)
    if resolved is ChunkStrategy.SENTENCE:
        units = _split_oversized_units(_split_sentences(normalized), chunk_size, overlap)
        return _merge_units(units, chunk_size, overlap, separator="\n")
    if resolved is ChunkStrategy.MARKDOWN:
        return _markdown_chunks(normalized, chunk_size, overlap)

    paragraphs = _split_paragraphs(normalized)
    units = _split_oversized_units(paragraphs, chunk_size, overlap)
    return _merge_units(units, chunk_size, overlap, separator="\n")


def _split_paragraphs(text: str) -> list[str]:
    """按空行切分段落并过滤空白段。"""
    return [
        paragraph.strip()
        for paragraph in _PARAGRAPH_SPLIT_PATTERN.split(text)
        if paragraph.strip()
    ]


def _split_sentences(text: str) -> list[str]:
    """按中英文句末标点或换行切分句子，过滤空白句。"""
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT_PATTERN.split(text)
        if sentence.strip()
    ]


def _split_oversized_units(units: list[str], chunk_size: int, overlap: int) -> list[str]:
    """超长单元按「窗口 chunk_size、步长 chunk_size - overlap」切分，短单元原样保留。"""
    result: list[str] = []
    step = chunk_size - overlap
    for unit in units:
        if len(unit) <= chunk_size:
            result.append(unit)
            continue
        for start in range(0, len(unit), step):
            piece = unit[start : start + chunk_size].strip()
            if piece:
                result.append(piece)
            if start + chunk_size >= len(unit):
                break
    return result


def _merge_units(
    units: list[str],
    chunk_size: int,
    overlap: int,
    separator: str,
) -> list[str]:
    """合并相邻单元为分块，块间用上一块尾部拼接实现重叠。"""
    chunks: list[str] = []
    current = ""

    for unit in units:
        candidate = f"{current}{separator}{unit}" if current else unit
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if chunks and overlap > 0:
            tail = chunks[-1][-overlap:]
            with_overlap = f"{tail}{separator}{unit}"
            # 单元本身占满窗口时无法再容纳重叠，直接以单元开新块
            current = with_overlap if len(with_overlap) <= chunk_size else unit
        else:
            current = unit

    if current:
        chunks.append(current)
    return chunks


def _fixed_window_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """固定窗口滑动切分：不看段落/句子边界，相邻窗口重叠 overlap 个字符。"""
    step = chunk_size - overlap
    chunks: list[str] = []
    for start in range(0, len(text), step):
        piece = text[start : start + chunk_size].strip()
        if piece:
            chunks.append(piece)
        if start + chunk_size >= len(text):
            break
    return chunks


def _markdown_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """按 Markdown 标题切分小节；无标题时退化为段落策略，超长小节再按段落切分。"""
    if not _MARKDOWN_HEADING_PATTERN.search(text):
        units = _split_oversized_units(_split_paragraphs(text), chunk_size, overlap)
        return _merge_units(units, chunk_size, overlap, separator="\n")

    sections = [
        section.strip()
        for section in _MARKDOWN_HEADING_SPLIT_PATTERN.split(text)
        if section.strip()
    ]
    chunks: list[str] = []
    for section in sections:
        if len(section) <= chunk_size:
            chunks.append(section)
            continue
        units = _split_oversized_units(_split_paragraphs(section), chunk_size, overlap)
        chunks.extend(_merge_units(units, chunk_size, overlap, separator="\n"))
    return chunks
