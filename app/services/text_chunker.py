"""文本分块器：段落优先 + 固定窗口 + 重叠。

策略：
1. 先按空行切分段落，短段落尽量合并进同一块，减少语义被切断；
2. 单个超长段落按「窗口大小 chunk_size、步长 chunk_size - overlap」滑动切分，
   相邻窗口天然重叠 overlap 个字符；
3. 跨段落合并块时，新块开头拼接上一块末尾 overlap 个字符，保持上下文连续。

保证：每个分块长度不超过 ``chunk_size``（除非单段本身超长且无法容纳重叠）。
"""

import re

DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50

# 空行（含仅空白行）分隔段落
_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n")


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """将纯文本切分为带重叠的分块列表，空文本返回空列表。

    :param text: 待切分文本
    :param chunk_size: 单块最大字符数
    :param overlap: 相邻块重叠字符数，需小于 chunk_size
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size 必须为正整数，当前值：{chunk_size}")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(f"overlap 必须满足 0 <= overlap < chunk_size，当前值：{overlap}")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    paragraphs = [
        paragraph.strip()
        for paragraph in _PARAGRAPH_SPLIT_PATTERN.split(normalized)
        if paragraph.strip()
    ]
    units = _build_units(paragraphs, chunk_size, overlap)
    return _merge_units(units, chunk_size, overlap)


def _build_units(paragraphs: list[str], chunk_size: int, overlap: int) -> list[str]:
    """段落转单元：短段落原样保留，超长段落按窗口切分。"""
    units: list[str] = []
    step = chunk_size - overlap
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            units.append(paragraph)
            continue
        for start in range(0, len(paragraph), step):
            piece = paragraph[start : start + chunk_size].strip()
            if piece:
                units.append(piece)
            if start + chunk_size >= len(paragraph):
                break
    return units


def _merge_units(units: list[str], chunk_size: int, overlap: int) -> list[str]:
    """合并相邻单元为分块，块间用上一块尾部拼接实现重叠。"""
    chunks: list[str] = []
    current = ""

    for unit in units:
        candidate = f"{current}\n{unit}" if current else unit
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if chunks and overlap > 0:
            tail = chunks[-1][-overlap:]
            with_overlap = f"{tail}\n{unit}"
            # 单元本身占满窗口时无法再容纳重叠，直接以单元开新块
            current = with_overlap if len(with_overlap) <= chunk_size else unit
        else:
            current = unit

    if current:
        chunks.append(current)
    return chunks
