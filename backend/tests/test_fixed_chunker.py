from itertools import pairwise

import pytest

from crimescene.ingest.chunking_config import (
    ChunkingConfig,
    ChunkingMode,
)
from crimescene.ingest.fixed_chunker import split_fixed_text


def test_default_fixed_chunking():
    """1,800자 문서가 예상한 길이로 분할되는지 확인."""

    text = "A" * 1800
    config = ChunkingConfig()

    chunks = split_fixed_text(text, config)

    assert len(chunks) == 3
    assert [len(chunk) for chunk in chunks] == [800, 800, 360]


def test_short_document_preserved():
    """짧은 문서는 원본을 그대로 유지."""

    text = "신기범 사건 관련 조사 기록입니다."

    chunks = split_fixed_text(text, ChunkingConfig())

    assert chunks == [text]


def test_document_equal_to_max_size():
    """최대 크기와 같은 문서는 분할하지 않는다."""

    text = "가" * 800

    chunks = split_fixed_text(text, ChunkingConfig())

    assert chunks == [text]


def test_document_one_char_over_max():
    """최대 크기를 1자 초과하는 문서 분할."""

    text = "A" * 801

    chunks = split_fixed_text(text, ChunkingConfig())

    assert len(chunks) == 2
    assert all(len(chunk) <= 800 for chunk in chunks)
    assert len(chunks[-1]) >= 120


def test_overlap_content():
    """인접한 청크 사이에 80자 Overlap 적용."""

    text = "".join(f"{i:04d}" for i in range(450))

    chunks = split_fixed_text(text, ChunkingConfig())

    assert len(chunks) == 3

    assert chunks[0] == text[0:800]
    assert chunks[1] == text[720:1520]
    assert chunks[2] == text[1440:1800]

    assert chunks[0][-80:] == chunks[1][:80]
    assert chunks[1][-80:] == chunks[2][:80]


def test_chunking_without_overlap():
    """Overlap이 0인 경우 중복 없이 분할."""

    config = ChunkingConfig(
        mode=ChunkingMode.FIXED,
        min_chunk_chars=60,
        max_chunk_chars=200,
        overlap_chars=0,
    )

    text = "ABCD" * 135

    chunks = split_fixed_text(text, config)

    assert [len(chunk) for chunk in chunks] == [
        200,
        200,
        140,
    ]

    assert "".join(chunks) == text


def test_last_chunk_minimum_size():
    """마지막 청크가 너무 짧으면 경계를 조정한다."""

    config = ChunkingConfig(
        min_chunk_chars=120,
        max_chunk_chars=800,
        overlap_chars=80,
    )

    text = "A" * 801

    chunks = split_fixed_text(text, config)

    assert len(chunks) == 2
    assert len(chunks[0]) == 761
    assert len(chunks[1]) == 120


@pytest.mark.parametrize(
    "length",
    [
        1,
        100,
        799,
        800,
        801,
        805,
        820,
        850,
        1600,
        1800,
        2500,
    ],
)
def test_no_text_loss(length: int):
    """다양한 문서 길이에서 원본 복원 가능 여부 확인."""

    config = ChunkingConfig()

    pattern = "가나abc\n "

    text = (pattern * ((length // len(pattern)) + 1))[:length]

    chunks = split_fixed_text(text, config)

    assert chunks

    # 모든 청크가 최대 크기 이하여야 한다.
    assert all(len(chunk) <= config.max_chunk_chars for chunk in chunks)

    # 인접 청크의 Overlap이 동일해야 한다.
    for previous, current in pairwise(chunks):
        assert previous[-config.overlap_chars :] == current[: config.overlap_chars]

    # Overlap을 제거하면 원본 텍스트가 복원되어야 한다.
    reconstructed = chunks[0] + "".join(
        chunk[config.overlap_chars :] for chunk in chunks[1:]
    )

    assert reconstructed == text


def test_original_whitespace_preserved():
    """원본 앞뒤 공백과 줄바꿈을 보존한다."""

    text = "  첫 번째 기록\n\n두 번째 기록  "

    chunks = split_fixed_text(text, ChunkingConfig())

    assert chunks == [text]


def test_short_npc_statement():
    """짧은 NPC 진술은 강제로 분할하지 않는다."""

    text = "그날 저는 학교에 있었습니다."

    chunks = split_fixed_text(text, ChunkingConfig())

    assert len(chunks) == 1
    assert chunks[0] == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "\n\t ",
    ],
)
def test_empty_text_rejected(text: str):
    """빈 문자열 및 공백만 있는 문자열 차단."""

    with pytest.raises(
        ValueError,
        match="청킹할 텍스트가 비어 있습니다",
    ):
        split_fixed_text(text, ChunkingConfig())


@pytest.mark.parametrize(
    "invalid_input",
    [
        None,
        123,
        ["문서"],
    ],
)
def test_invalid_input_type(invalid_input):
    """문자열이 아닌 데이터 입력 차단."""

    with pytest.raises(
        TypeError,
        match="청킹 대상은 문자열이어야 합니다",
    ):
        split_fixed_text(invalid_input, ChunkingConfig())
