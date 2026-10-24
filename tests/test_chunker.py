"""分块器单元测试：空文本、短文本、长文本窗口与重叠、段落合并、参数校验。"""

import pytest

from app.services.text_chunker import chunk_text


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


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (-1, 0), (500, -1), (500, 500), (500, 600)],
)
def test_invalid_parameters_raise_value_error(chunk_size: int, overlap: int) -> None:
    """非法窗口/重叠参数直接报错，避免静默生成异常分块。"""
    with pytest.raises(ValueError):
        chunk_text("任意文本", chunk_size=chunk_size, overlap=overlap)
