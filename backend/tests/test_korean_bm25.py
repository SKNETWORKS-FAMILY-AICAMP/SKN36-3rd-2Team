"""한국어 BM25 Sparse Encoder 단위 테스트."""

import math

import pytest
from kiwipiepy import Kiwi
from qdrant_client import models

from crimescene.retriever.korean_bm25 import (
    KoreanBM25Encoder,
)


@pytest.fixture(scope="module")
def kiwi():
    """테스트에서 Kiwi 모델을 재사용한다."""

    return Kiwi()


@pytest.fixture
def encoder(kiwi):
    """테스트용 BM25 Encoder."""

    return KoreanBM25Encoder(kiwi=kiwi)


def test_korean_tokenization(encoder):
    """한국어 조사와 어미를 제거하고 키워드를 추출한다."""

    tokens = encoder.tokenize("신기범은 사건 당일 학교에 방문했습니다.")

    assert "신기범" in tokens
    assert "사건" in tokens
    assert "당일" in tokens
    assert "학교" in tokens
    assert "방문" in tokens

    assert "은" not in tokens
    assert "에" not in tokens
    assert "습니다" not in tokens


def test_token_id_is_deterministic(encoder):
    """같은 키워드는 항상 동일한 ID를 생성한다."""

    first = encoder.token_id("신기범")
    second = encoder.token_id("신기범")

    other_encoder = KoreanBM25Encoder()

    third = other_encoder.token_id("신기범")

    assert first == second == third


def test_token_id_is_uint32(encoder):
    """키워드 ID는 32비트 부호 없는 정수 범위다."""

    for word in ["신기범", "학교", "사건", "증거"]:
        index = encoder.token_id(word)

        assert isinstance(index, int)
        assert 0 <= index < 2**32


def test_average_document_length(encoder):
    """전체 문서의 평균 토큰 길이를 계산한다."""

    documents = [
        "신기범 학교 출입 기록",
        "사건 당일 목격자 진술",
        "학교 사건 조사",
    ]

    expected = sum(len(encoder.tokenize(text)) for text in documents) / len(documents)

    encoder.fit(documents)

    assert encoder.avg_document_length == pytest.approx(expected)


def test_encode_multiple_documents(encoder):
    """여러 문서를 Sparse Vector로 변환한다."""

    documents = [
        "신기범 학교 출입 기록",
        "사건 당일 목격자 진술",
        "학교 출입 증거",
    ]

    vectors = encoder.encode_documents(documents)

    assert len(vectors) == 3

    for vector in vectors:
        assert isinstance(vector, models.SparseVector)
        assert len(vector.indices) == len(vector.values)
        assert len(vector.indices) > 0

        assert vector.indices == sorted(vector.indices)

        assert all(math.isfinite(value) and value > 0 for value in vector.values)


def test_query_encoding_removes_duplicates(encoder):
    """질문에서 반복된 키워드는 하나의 ID로 처리한다."""

    query = encoder.encode_query("학교 학교 기록")

    expected_ids = {
        encoder.token_id("학교"),
        encoder.token_id("기록"),
    }

    assert set(query.indices) == expected_ids
    assert len(query.indices) == 2
    assert query.values == [1.0, 1.0]


def test_document_query_ids_match(encoder):
    """문서와 질문에 등장하는 동일 키워드의 ID는 일치한다."""

    document = "신기범 학교 출입 기록"
    question = "신기범의 학교 기록"

    document_vector = encoder.encode_documents([document])[0]

    query_vector = encoder.encode_query(question)

    document_ids = set(document_vector.indices)
    query_ids = set(query_vector.indices)

    expected_ids = {
        encoder.token_id("신기범"),
        encoder.token_id("학교"),
        encoder.token_id("기록"),
    }

    assert expected_ids.issubset(document_ids)
    assert expected_ids.issubset(query_ids)


def test_higher_term_frequency_increases_weight(encoder):
    """문서 길이가 같을 때 키워드 빈도가 높으면 가중치가 증가한다."""

    documents = [
        "학교 학교 기록",
        "학교 기록 기록",
    ]

    vectors = encoder.encode_documents(documents)

    school_id = encoder.token_id("학교")

    first = dict(
        zip(
            vectors[0].indices,
            vectors[0].values,
            strict=True,
        )
    )

    second = dict(
        zip(
            vectors[1].indices,
            vectors[1].values,
            strict=True,
        )
    )

    assert first[school_id] > second[school_id]


def test_document_encoding_requires_fit(encoder):
    """평균 문서 길이를 계산하기 전에 인코딩할 수 없다."""

    with pytest.raises(
        RuntimeError,
        match="fit",
    ):
        encoder.encode_document("신기범 학교 출입 기록")


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("k1", 0),
        ("k1", -1),
        ("k1", float("nan")),
        ("k1", float("inf")),
        ("k1", True),
        ("b", -0.1),
        ("b", 1.1),
        ("b", float("nan")),
        ("b", False),
    ],
)
def test_invalid_parameters_rejected(
    kiwi,
    parameter,
    value,
):
    """잘못된 BM25 파라미터를 차단한다."""

    with pytest.raises(ValueError):
        KoreanBM25Encoder(
            kiwi=kiwi,
            **{parameter: value},
        )


@pytest.mark.parametrize(
    ("text", "error_type"),
    [
        (None, TypeError),
        (123, TypeError),
        ("", ValueError),
        ("   ", ValueError),
        ("!!!", ValueError),
    ],
)
def test_invalid_tokenization_input(
    encoder,
    text,
    error_type,
):
    """유효하지 않은 텍스트 입력을 차단한다."""

    with pytest.raises(error_type):
        encoder.tokenize(text)


@pytest.mark.parametrize(
    ("documents", "error_type"),
    [
        ([], ValueError),
        ("학교 기록", TypeError),
        (None, TypeError),
        (123, TypeError),
    ],
)
def test_invalid_corpus_rejected(
    encoder,
    documents,
    error_type,
):
    """잘못된 전체 문서 목록을 차단한다."""

    with pytest.raises(error_type):
        encoder.fit(documents)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "!!!",
    ],
)
def test_empty_query_rejected(
    encoder,
    query,
):
    """검색 키워드가 없는 질문을 차단한다."""

    with pytest.raises(ValueError):
        encoder.encode_query(query)


def test_token_hash_collision_rejected(
    encoder,
    monkeypatch,
):
    """서로 다른 키워드의 해시 ID 충돌을 차단한다."""

    # 두 키워드가 같은 ID를 반환하도록 강제
    monkeypatch.setattr(
        KoreanBM25Encoder,
        "token_id",
        staticmethod(lambda token: 42),
    )

    with pytest.raises(
        ValueError,
        match="충돌",
    ):
        encoder.encode_query("학교 기록")
