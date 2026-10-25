"""分块器单元测试：空文本、短文本、长文本窗口与重叠、段落合并、各分块策略、参数校验。"""

import pytest

from app.services.text_chunker import ChunkStrategy, chunk_text


def test_empty_text_returns_empty_list() -> None:
    """空文本与纯空白文本返回空列表。"""
    assert chunk_text("") == []
    assert chunk_text("   \n\n \t  ") == []


def test_short_text_returns_single_chunk() -> None:
    """短文本原样作为一个分块返回。"""
    text = "这是一段很短的文本。"
    chunks = chunk_text(text)

    assert chunks == [text]


def test_text_with_crlf_normalized() -> None:
    """CRLF/CR 统一为 LF，合并后的分块内容稳定。"""
    chunks = chunk_text("第一段\r\n\r\n第二段\r内容")

    assert chunks == ["第一段\n第二段\n内容"]


def test_long_paragraph_windows_and_overlap() -> None:
    """超长单段按 500 字窗口、50 字重叠切分，相邻块重叠正确且不超长。"""
    text = "".join(str(index % 10) for index in range(1200))
    chunks = chunk_text(text, chunk_size=500, overlap=50)

    assert len(chunks) == 3
    assert all(len(chunk) <= 500 for chunk in chunks)
    # 窗口步长 450：第二块开头应与第一块末尾 50 字一致，第三块同理
    assert chunks[1][:50] == chunks[0][-50:]
    assert chunks[2][:50] == chunks[1][-50:]
    # 覆盖到全文末尾
    assert chunks[-1][-1] == text[-1]


def test_short_paragraphs_merged_into_one_chunk() -> None:
    """多个短段落优先合并，总长不超过窗口时只生成一个分块。"""
    text = "段落一\n\n段落二\n\n段落三"
    chunks = chunk_text(text, chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert "段落一" in chunks[0]
    assert "段落三" in chunks[0]


def test_overlap_between_merged_paragraph_chunks() -> None:
    """跨段落合并产生新块时，新块开头携带上一块末尾的重叠内容。"""
    first = "a" * 300
    second = "b" * 300
    chunks = chunk_text(f"{first}\n\n{second}", chunk_size=500, overlap=50)

    assert len(chunks) == 2
    assert chunks[0] == first
    assert chunks[1].startswith("a" * 50)
    assert second in chunks[1]
    assert len(chunks[1]) <= 500


def test_zero_overlap_disabled() -> None:
    """overlap=0 时块间不产生重叠内容。"""
    first = "a" * 300
    second = "b" * 300
    chunks = chunk_text(f"{first}\n\n{second}", chunk_size=500, overlap=0)

    assert chunks == [first, second]


def test_fixed_strategy_slides_without_structure() -> None:
    """固定窗口策略忽略段落边界，按窗口滑动并保持重叠。"""
    text = "a" * 300 + "\n\n" + "b" * 300
    chunks = chunk_text(
        text, chunk_size=500, overlap=50, strategy=ChunkStrategy.FIXED
    )

    assert len(chunks) == 2
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert chunks[0].startswith("a" * 300)
    assert chunks[1][:50] == chunks[0][-50:]


def test_sentence_strategy_keeps_sentence_boundaries() -> None:
    """句子策略按句末标点聚合，不把句子从中间切断。"""
    text = "第一句话。第二句话。第三句话。"
    chunks = chunk_text(text, chunk_size=12, overlap=0, strategy="sentence")

    assert chunks == ["第一句话。\n第二句话。", "第三句话。"]


def test_sentence_strategy_splits_oversized_sentence() -> None:
    """单句长度超过窗口时仍需按窗口切分，保证分块不超长。"""
    text = "a" * 1200
    chunks = chunk_text(text, chunk_size=500, overlap=50, strategy="sentence")

    assert len(chunks) == 3
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert chunks[1][:50] == chunks[0][-50:]


def test_markdown_strategy_splits_by_headings() -> None:
    """Markdown 策略按标题切分小节，标题保留在所属小节内。"""
    text = "# 标题一\n内容一\n\n## 标题二\n内容二"
    chunks = chunk_text(text, chunk_size=20, overlap=0, strategy="markdown")

    assert chunks == ["# 标题一\n内容一", "## 标题二\n内容二"]


def test_markdown_strategy_splits_long_section_within_limit() -> None:
    """超长小节继续按段落切分，所有分块均不超过窗口大小。"""
    body = "\n\n".join(["段落" * 100] * 3)
    text = f"# 标题\n{body}"
    chunks = chunk_text(text, chunk_size=300, overlap=20, strategy="markdown")

    assert len(chunks) >= 3
    assert all(len(chunk) <= 300 for chunk in chunks)
    assert chunks[0].startswith("# 标题")


def test_markdown_strategy_falls_back_without_headings() -> None:
    """无 Markdown 标题时退化为段落优先策略，避免整篇只能作为一块。"""
    text = "段落一\n\n段落二"
    chunks = chunk_text(text, chunk_size=500, overlap=50, strategy="markdown")

    assert chunks == ["段落一\n段落二"]


def test_invalid_strategy_raises_value_error() -> None:
    """未知分块策略直接报错，避免静默回退到默认策略。"""
    with pytest.raises(ValueError):
        chunk_text("任意文本", strategy="unknown")


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (-1, 0), (500, -1), (500, 500), (500, 600)],
)
def test_invalid_parameters_raise_value_error(chunk_size: int, overlap: int) -> None:
    """非法窗口/重叠参数直接报错，避免静默生成异常分块。"""
    with pytest.raises(ValueError):
        chunk_text("任意文本", chunk_size=chunk_size, overlap=overlap)
