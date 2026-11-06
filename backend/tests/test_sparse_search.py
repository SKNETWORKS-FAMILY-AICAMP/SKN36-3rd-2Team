"""Qdrant 한국어 BM25 Sparse 검색 단위 테스트."""

import math
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import NAMESPACE_URL, uuid5

import pytest
from qdrant_client import QdrantClient, models

from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    SPARSE_VECTOR_NAME,
    ensure_qdrant_collection,
)
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.sparse_search import (
    SparseSearchCandidate,
    search_sparse_candidates,
)

DOCUMENTS = [
    (
        "DOC-A",
        "신기범 학교 출입 기록 기록 출입",
        "CASE-001",
        "player_document",
        None,
    ),
    (
        "DOC-B",
        "목격자 진술 교무실 회의",
        "CASE-001",
        "player_document",
        None,
    ),
    (
        "DOC-C",
        "교실 출입 교사 확인",
        "CASE-001",
        "player_document",
        None,
    ),
    (
        "DOC-OTHER",
        "학교 출입 기록",
        "CASE-999",
        "player_document",
        None,
    ),
    (
        "NPC-C01",
        "신기범 비밀 진술",
        "CASE-001",
        "npc_knowledge",
        "C01",
    ),
    (
        "NPC-C02",
        "신기범 목격 진술",
        "CASE-001",
        "npc_knowledge",
        "C02",
    ),
]


def point_id(name: str) -> str:
    """테스트 Point UUID."""

    return str(uuid5(NAMESPACE_URL, name))


@pytest.fixture(scope="module")
def encoder():
    """한국어 BM25 Encoder."""

    return KoreanBM25Encoder()


@pytest.fixture
def client(encoder):
    """Dense 및 Sparse Vector를 가진 인메모리 Qdrant."""

    qdrant = QdrantClient(":memory:")

    ensure_qdrant_collection(qdrant)

    texts = [document[1] for document in DOCUMENTS]

    sparse_vectors = encoder.encode_documents(texts)

    points = []

    for document, sparse in zip(
        DOCUMENTS,
        sparse_vectors,
        strict=True,
    ):
        name, _, case_id, source_type, character_id = document

        points.append(
            models.PointStruct(
                id=point_id(name),
                vector={
                    DENSE_VECTOR_NAME: ([0.1] * DENSE_VECTOR_SIZE),
                    SPARSE_VECTOR_NAME: sparse,
                },
                payload={
                    "case_id": case_id,
                    "source_type": source_type,
                    "character_id": character_id,
                    "source_id": name,
                    "body": "테스트용 비공개 본문",
                },
            )
        )

    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
        wait=True,
    )

    yield qdrant

    qdrant.close()


def search_player(query, client, encoder, **kwargs):
    """플레이어 문서 검색 편의 함수."""

    return search_sparse_candidates(
        query,
        client=client,
        encoder=encoder,
        source_type="player_document",
        **kwargs,
    )


def test_korean_keyword_search(client, encoder):
    """한국어 키워드로 관련 문서를 검색한다."""

    results = search_player(
        "신기범 학교 출입 기록",
        client,
        encoder,
    )

    assert results

    assert all(isinstance(item, SparseSearchCandidate) for item in results)

    assert results[0].point_id == point_id("DOC-A")


def test_bm25_ranking(client, encoder):
    """관련 키워드가 많은 문서를 상위에 반환한다."""

    results = search_player(
        "출입 기록",
        client,
        encoder,
    )

    assert len(results) >= 2

    assert results[0].point_id == point_id("DOC-A")

    assert all(
        results[index].score >= results[index + 1].score
        for index in range(len(results) - 1)
    )


def test_top_k_limit(client, encoder):
    """검색 결과 개수를 제한한다."""

    results = search_player(
        "출입 기록",
        client,
        encoder,
        top_k=1,
    )

    assert len(results) == 1


def test_other_case_excluded(client, encoder):
    """다른 사건의 문서는 검색 결과에서 제외한다."""

    results = search_player(
        "학교 출입 기록",
        client,
        encoder,
    )

    ids = {item.point_id for item in results}

    assert point_id("DOC-OTHER") not in ids


def test_unknown_case_returns_empty(client, encoder):
    """존재하지 않는 사건 검색 시 빈 목록을 반환한다."""

    results = search_player(
        "학교 기록",
        client,
        encoder,
        case_id="CASE-888",
    )

    assert results == []


def test_player_document_filter(client, encoder):
    """플레이어 문서 검색에서 NPC 지식을 제외한다."""

    results = search_player(
        "신기범",
        client,
        encoder,
    )

    ids = {item.point_id for item in results}

    assert point_id("DOC-A") in ids
    assert point_id("NPC-C01") not in ids
    assert point_id("NPC-C02") not in ids


@pytest.mark.parametrize(
    ("character_id", "expected_name"),
    [
        ("C01", "NPC-C01"),
        ("C02", "NPC-C02"),
    ],
)
def test_npc_character_filter(
    client,
    encoder,
    character_id,
    expected_name,
):
    """해당 NPC의 지식만 검색 후보로 반환한다."""

    results = search_sparse_candidates(
        "신기범",
        client=client,
        encoder=encoder,
        source_type="npc_knowledge",
        character_id=character_id,
    )

    assert len(results) == 1
    assert results[0].point_id == point_id(expected_name)


def test_candidate_contains_no_payload(client, encoder):
    """검색 후보에는 UUID와 점수만 포함한다."""

    results = search_player(
        "신기범 학교 기록",
        client,
        encoder,
    )

    assert results

    for item in results:
        assert set(asdict(item)) == {
            "point_id",
            "score",
        }

        assert math.isfinite(item.score)


def test_qdrant_payload_not_requested(client, encoder):
    """Qdrant 조회 시 본문과 벡터를 요청하지 않는다."""

    mock_client = Mock(wraps=client)

    search_player(
        "학교 기록",
        mock_client,
        encoder,
    )

    arguments = mock_client.query_points.call_args.kwargs

    assert arguments["with_payload"] is False
    assert arguments["with_vectors"] is False
    assert arguments["using"] == SPARSE_VECTOR_NAME


def test_query_is_trimmed(client, encoder):
    """질문 양쪽 공백을 제거한 뒤 인코딩한다."""

    mock_encoder = Mock(spec=KoreanBM25Encoder)

    mock_encoder.encode_query.return_value = encoder.encode_query("학교 기록")

    search_player(
        "  학교 기록  ",
        client,
        mock_encoder,
    )

    mock_encoder.encode_query.assert_called_once_with("학교 기록")


def test_search_does_not_modify_points(client, encoder):
    """검색 과정에서 저장된 Point를 수정하지 않는다."""

    before = client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count

    search_player(
        "신기범 기록",
        client,
        encoder,
    )

    after = client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count

    assert before == after == len(DOCUMENTS)


@pytest.mark.parametrize(
    ("query", "error_type"),
    [
        ("", ValueError),
        ("   ", ValueError),
        (None, TypeError),
        (123, TypeError),
    ],
)
def test_invalid_query_rejected(
    client,
    encoder,
    query,
    error_type,
):
    """잘못된 검색 질문을 차단한다."""

    with pytest.raises(error_type):
        search_player(
            query,
            client,
            encoder,
        )


@pytest.mark.parametrize(
    ("top_k", "error_type"),
    [
        (0, ValueError),
        (-1, ValueError),
        (101, ValueError),
        (True, TypeError),
        ("10", TypeError),
    ],
)
def test_invalid_top_k_rejected(
    client,
    encoder,
    top_k,
    error_type,
):
    """잘못된 검색 개수를 차단한다."""

    with pytest.raises(error_type):
        search_player(
            "학교 기록",
            client,
            encoder,
            top_k=top_k,
        )


@pytest.mark.parametrize(
    "case_id",
    ["", "   ", None],
)
def test_invalid_case_id_rejected(
    client,
    encoder,
    case_id,
):
    """유효하지 않은 사건 ID를 차단한다."""

    with pytest.raises(
        ValueError,
        match="사건 ID",
    ):
        search_player(
            "학교 기록",
            client,
            encoder,
            case_id=case_id,
        )


def test_invalid_source_type_rejected(client, encoder):
    """지원하지 않는 문서 유형을 차단한다."""

    with pytest.raises(
        ValueError,
        match="지원하지 않는 문서 유형",
    ):
        search_sparse_candidates(
            "학교 기록",
            client=client,
            encoder=encoder,
            source_type="unknown",
        )


def test_npc_requires_character_id(client, encoder):
    """NPC 검색에는 인물 ID가 필요하다."""

    with pytest.raises(
        ValueError,
        match="character_id",
    ):
        search_sparse_candidates(
            "신기범",
            client=client,
            encoder=encoder,
            source_type="npc_knowledge",
        )


def test_player_document_rejects_character_id(client, encoder):
    """플레이어 문서 검색에 NPC ID를 지정할 수 없다."""

    with pytest.raises(
        ValueError,
        match="character_id",
    ):
        search_player(
            "학교 기록",
            client,
            encoder,
            character_id="C01",
        )


def test_missing_keyword_rejected(client, encoder):
    """검색 키워드가 없는 질문은 거부한다."""

    with pytest.raises(ValueError):
        search_player(
            "!!!",
            client,
            encoder,
        )


def test_sparse_dimension_mismatch_rejected(client):
    """Sparse ID와 가중치 개수가 다르면 차단한다."""

    mock_encoder = Mock(spec=KoreanBM25Encoder)

    mock_encoder.encode_query.return_value = SimpleNamespace(
        indices=[1, 2],
        values=[1.0],
    )

    with pytest.raises(
        ValueError,
        match="크기가 일치하지 않습니다",
    ):
        search_player(
            "학교 기록",
            client,
            mock_encoder,
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_finite_sparse_value_rejected(
    client,
    invalid_value,
):
    """NaN과 Infinity Sparse 가중치를 차단한다."""

    mock_encoder = Mock(spec=KoreanBM25Encoder)

    mock_encoder.encode_query.return_value = SimpleNamespace(
        indices=[1],
        values=[invalid_value],
    )

    with pytest.raises(
        ValueError,
        match="유효하지 않은 Sparse Vector",
    ):
        search_player(
            "학교 기록",
            client,
            mock_encoder,
        )


def test_non_finite_search_score_rejected(encoder):
    """Qdrant가 비정상 점수를 반환하면 거부한다."""

    mock_client = Mock(spec=QdrantClient)

    mock_client.query_points.return_value = SimpleNamespace(
        points=[
            SimpleNamespace(
                id=point_id("DOC-A"),
                score=float("nan"),
            )
        ]
    )

    with pytest.raises(
        ValueError,
        match="유효하지 않은 검색 점수",
    ):
        search_player(
            "학교 기록",
            mock_client,
            encoder,
        )
