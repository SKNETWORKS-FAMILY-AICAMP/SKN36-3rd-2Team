import math

import pytest

from crimescene.ingest.chunking_config import (
    ChunkingConfig,
    ChunkingMode,
)
from crimescene.ingest.semantic_chunker import (
    cosine_similarity,
    normalize_embedding,
    split_semantic_text,
    split_sentence_units,
)


def make_config() -> ChunkingConfig:
    """Semantic Chunker 테스트용 설정."""

    return ChunkingConfig(
        mode=ChunkingMode.SEMANTIC_FIXED,
        min_chunk_chars=40,
        max_chunk_chars=180,
        overlap_chars=20,
        semantic_similarity_threshold=0.7,
    )


def make_long_text() -> str:
    """서로 다른 네 문장으로 구성된 테스트 문서."""

    return " ".join(
        [
            "A" * 60 + ".",
            "B" * 60 + ".",
            "C" * 60 + ".",
            "D" * 60 + ".",
        ]
    )


def test_sentence_split_preserves_original():
    """문장 분리 후 원본 텍스트가 보존되는지 확인."""

    text = (
        "  첫 번째 사건 기록입니다. "
        "두 번째 기록입니다!\n"
        "세 번째 진술입니다?\n\n"
        "  네 번째 기록입니다.  "
    )

    units = split_sentence_units(text)

    assert len(units) >= 3
    assert "".join(units) == text


def test_normalize_embedding():
    """임베딩 벡터 정규화."""

    result = normalize_embedding([3.0, 4.0])

    assert result == pytest.approx((0.6, 0.8))


@pytest.mark.parametrize(
    "vector",
    [
        [],
        [0.0, 0.0],
        [float("nan"), 1.0],
        [float("inf"), 1.0],
        ["invalid", 1.0],
    ],
)
def test_invalid_embedding_rejected(vector):
    """잘못된 임베딩 벡터 차단."""

    with pytest.raises(ValueError):
        normalize_embedding(vector)


@pytest.mark.parametrize(
    ("vector_a", "vector_b", "expected"),
    [
        ([1.0, 0.0], [1.0, 0.0], 1.0),
        ([1.0, 0.0], [0.0, 1.0], 0.0),
        ([1.0, 0.0], [-1.0, 0.0], -1.0),
    ],
)
def test_cosine_similarity(
    vector_a,
    vector_b,
    expected,
):
    """코사인 유사도 계산 검증."""

    similarity = cosine_similarity(
        vector_a,
        vector_b,
    )

    assert similarity == pytest.approx(expected)


def test_cosine_dimension_mismatch():
    """임베딩 차원 불일치 차단."""

    with pytest.raises(
        ValueError,
        match="임베딩 차원",
    ):
        cosine_similarity(
            [1.0, 0.0],
            [1.0, 0.0, 0.0],
        )


def test_semantic_groups_similar_sentences():
    """의미가 유사한 문장을 같은 청크로 묶는다."""

    text = make_long_text()

    def embed_sentences(sentences):
        assert len(sentences) == 4

        return [
            [1.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [0.0, 1.0],
        ]

    chunks = split_semantic_text(
        text,
        make_config(),
        embed_sentences,
    )

    assert len(chunks) == 2

    assert "A" * 60 in chunks[0]
    assert "B" * 60 in chunks[0]

    assert "C" * 60 in chunks[1]
    assert "D" * 60 in chunks[1]

    assert "".join(chunks) == text


def test_semantic_groups_different_sentences():
    """의미가 다른 문장들은 각각 분리한다."""

    text = make_long_text()

    def embed_sentences(sentences):
        assert len(sentences) == 4

        return [
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ]

    chunks = split_semantic_text(
        text,
        make_config(),
        embed_sentences,
    )

    assert len(chunks) == 4
    assert "".join(chunks) == text


def test_long_semantic_group_uses_fixed_chunking():
    """긴 의미 그룹은 Fixed-size로 추가 분할한다."""

    text = make_long_text()
    config = make_config()

    def embed_sentences(sentences):
        return [[1.0, 0.0] for _ in sentences]

    chunks = split_semantic_text(
        text,
        config,
        embed_sentences,
    )

    assert len(chunks) == 2

    assert all(len(chunk) <= config.max_chunk_chars for chunk in chunks)

    assert chunks[0][-config.overlap_chars :] == chunks[1][: config.overlap_chars]

    reconstructed = chunks[0] + chunks[1][config.overlap_chars :]

    assert reconstructed == text


def test_no_sentence_boundary_uses_fixed_chunking():
    """문장 경계가 없으면 Fixed-size를 사용한다."""

    text = "A" * 350
    config = make_config()

    def embed_sentences(_):
        pytest.fail("문장 경계가 없으면 임베딩을 호출하면 안 됩니다.")

    chunks = split_semantic_text(
        text,
        config,
        embed_sentences,
    )

    assert len(chunks) > 1

    reconstructed = chunks[0] + "".join(
        chunk[config.overlap_chars :] for chunk in chunks[1:]
    )

    assert reconstructed == text


def test_short_document_preserved():
    """짧은 문서는 임베딩 없이 원본 유지."""

    text = "신기범 사건 관련 짧은 기록입니다."

    def embed_sentences(_):
        pytest.fail("짧은 문서는 임베딩을 호출하면 안 됩니다.")

    chunks = split_semantic_text(
        text,
        make_config(),
        embed_sentences,
    )

    assert chunks == [text]


def test_invalid_chunking_mode():
    """Semantic Fixed 모드가 아니면 차단."""

    config = ChunkingConfig(
        mode=ChunkingMode.FIXED,
        min_chunk_chars=40,
        max_chunk_chars=180,
        overlap_chars=20,
    )

    with pytest.raises(
        ValueError,
        match="semantic_fixed",
    ):
        split_semantic_text(
            make_long_text(),
            config,
            lambda sentences: [[1.0, 0.0] for _ in sentences],
        )


def test_embedding_count_mismatch():
    """문장 수와 임베딩 개수가 다르면 차단."""

    with pytest.raises(
        ValueError,
        match="문장 수와 임베딩 수",
    ):
        split_semantic_text(
            make_long_text(),
            make_config(),
            lambda _: [[1.0, 0.0]],
        )


def test_embedding_dimension_mismatch():
    """임베딩 벡터들의 차원이 다르면 차단."""

    embeddings = [
        [1.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0],
        [0.0, 1.0],
    ]

    with pytest.raises(
        ValueError,
        match="임베딩 차원",
    ):
        split_semantic_text(
            make_long_text(),
            make_config(),
            lambda _: embeddings,
        )


@pytest.mark.parametrize(
    "invalid_vector",
    [
        [0.0, 0.0],
        [math.nan, 1.0],
        [math.inf, 1.0],
    ],
)
def test_semantic_invalid_embedding(invalid_vector):
    """Semantic Chunker가 잘못된 임베딩을 거부한다."""

    embeddings = [
        [1.0, 0.0],
        invalid_vector,
        [0.0, 1.0],
        [0.0, 1.0],
    ]

    with pytest.raises(ValueError):
        split_semantic_text(
            make_long_text(),
            make_config(),
            lambda _: embeddings,
        )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_empty_text_rejected(text):
    """빈 문자열과 공백만 있는 문자열 차단."""

    with pytest.raises(
        ValueError,
        match="청킹할 텍스트가 비어 있습니다",
    ):
        split_semantic_text(
            text,
            make_config(),
            lambda _: [],
        )


@pytest.mark.parametrize(
    "invalid_input",
    [
        None,
        123,
        ["문서"],
    ],
)
def test_invalid_input_type(invalid_input):
    """문자열이 아닌 입력 차단."""

    with pytest.raises(
        TypeError,
        match="청킹 대상은 문자열이어야 합니다",
    ):
        split_semantic_text(
            invalid_input,
            make_config(),
            lambda _: [],
        )
