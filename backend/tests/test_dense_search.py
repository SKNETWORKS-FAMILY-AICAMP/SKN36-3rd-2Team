"""Qdrant Dense Vector 검색 단위 테스트."""

import math
from dataclasses import asdict
from unittest.mock import Mock
from uuid import NAMESPACE_URL, uuid5

import pytest
from qdrant_client import QdrantClient, models

from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    ensure_qdrant_collection,
)
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.dense_search import (
    DenseSearchCandidate,
    search_dense_candidates,
)


def make_vector(first: float, second: float) -> list[float]:
    """1024차원 테스트 벡터."""

    return [
        first,
        second,
        *([0.0] * (DENSE_VECTOR_SIZE - 2)),
    ]


def make_point(
    point_name: str,
    *,
    vector: list[float],
    case_id: str = "CASE-001",
    source_type: str = "player_document",
    character_id: str | None = None,
) -> models.PointStruct:
    """테스트용 Qdrant Point 생성."""

    point_id = uuid5(NAMESPACE_URL, point_name)

    return models.PointStruct(
        id=str(point_id),
        vector={
            DENSE_VECTOR_NAME: vector,
        },
        payload={
            "case_id": case_id,
            "source_type": source_type,
            "character_id": character_id,
            "source_id": point_name,
            "body": "테스트용 비공개 본문",
        },
    )


@pytest.fixture
def client():
    """테스트 전용 인메모리 Qdrant."""

    qdrant = QdrantClient(":memory:")

    ensure_qdrant_collection(qdrant)

    points = [
        # CASE-001 플레이어 문서
        make_point(
            "DOC-001",
            vector=make_vector(1.0, 0.0),
        ),
        make_point(
            "DOC-002",
            vector=make_vector(0.0, 1.0),
        ),
        # 다른 사건의 문서
        make_point(
            "OTHER-CASE",
            vector=make_vector(1.0, 0.0),
            case_id="CASE-999",
        ),
        # NPC C01 지식
        make_point(
            "NPC-C01",
            vector=make_vector(1.0, 0.0),
            source_type="npc_knowledge",
            character_id="C01",
        ),
        # NPC C02 지식
        make_point(
            "NPC-C02",
            vector=make_vector(1.0, 0.0),
            source_type="npc_knowledge",
            character_id="C02",
        ),
    ]

    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
        wait=True,
    )

    yield qdrant

    qdrant.close()


@pytest.fixture
def embedder():
    """실제 Ollama 대신 사용하는 Mock."""

    mock = Mock(spec=OllamaEmbedder)

    mock.embed_query.return_value = make_vector(
        1.0,
        0.0,
    )

    return mock


def point_id(name: str) -> str:
    """테스트 Point UUID."""

    return str(uuid5(NAMESPACE_URL, name))


def test_dense_search_returns_candidates(client, embedder):
    """한국어 질문으로 검색 후보를 반환한다."""

    results = search_dense_candidates(
        "신기범의 사건 기록",
        client=client,
        embedder=embedder,
        source_type="player_document",
    )

    assert len(results) == 2

    assert all(isinstance(item, DenseSearchCandidate) for item in results)


def test_cosine_similarity_ranking(client, embedder):
    """Cosine 유사도가 높은 문서를 우선 반환한다."""

    results = search_dense_candidates(
        "사건 기록 검색",
        client=client,
        embedder=embedder,
        source_type="player_document",
    )

    assert results[0].point_id == point_id("DOC-001")
    assert results[1].point_id == point_id("DOC-002")

    assert results[0].score > results[1].score


def test_top_k_limit(client, embedder):
    """검색 결과 개수를 제한한다."""

    results = search_dense_candidates(
        "사건 기록",
        client=client,
        embedder=embedder,
        source_type="player_document",
        top_k=1,
    )

    assert len(results) == 1


def test_other_case_excluded(client, embedder):
    """다른 사건의 문서는 검색 결과에서 제외한다."""

    results = search_dense_candidates(
        "사건 기록",
        client=client,
        embedder=embedder,
        source_type="player_document",
        case_id="CASE-001",
    )

    ids = {item.point_id for item in results}

    assert point_id("OTHER-CASE") not in ids


def test_unknown_case_returns_empty(client, embedder):
    """해당 사건 문서가 없으면 빈 목록을 반환한다."""

    results = search_dense_candidates(
        "사건 기록",
        client=client,
        embedder=embedder,
        source_type="player_document",
        case_id="CASE-888",
    )

    assert results == []


def test_player_document_filter(client, embedder):
    """플레이어 문서 검색에서 NPC 지식을 제외한다."""

    results = search_dense_candidates(
        "학교 출입 기록",
        client=client,
        embedder=embedder,
        source_type="player_document",
    )

    ids = {item.point_id for item in results}

    assert ids == {
        point_id("DOC-001"),
        point_id("DOC-002"),
    }


def test_npc_character_filter(client, embedder):
    """지정한 NPC의 지식만 검색한다."""

    results = search_dense_candidates(
        "사건 당일 무엇을 보았나요?",
        client=client,
        embedder=embedder,
        source_type="npc_knowledge",
        character_id="C01",
    )

    ids = {item.point_id for item in results}

    assert ids == {point_id("NPC-C01")}


def test_other_npc_excluded(client, embedder):
    """다른 인물의 NPC 지식을 검색 후보에서 제외한다."""

    results = search_dense_candidates(
        "목격자 진술",
        client=client,
        embedder=embedder,
        source_type="npc_knowledge",
        character_id="C02",
    )

    assert len(results) == 1
    assert results[0].point_id == point_id("NPC-C02")


def test_candidate_contains_no_payload(client, embedder):
    """검색 후보에는 본문과 내부 메타데이터가 없다."""

    results = search_dense_candidates(
        "사건 기록",
        client=client,
        embedder=embedder,
        source_type="player_document",
    )

    assert results

    for result in results:
        assert set(asdict(result)) == {
            "point_id",
            "score",
        }

        assert math.isfinite(result.score)


def test_query_is_trimmed(client, embedder):
    """질문 양쪽 공백을 제거해 임베딩한다."""

    search_dense_candidates(
        "  사건 기록  ",
        client=client,
        embedder=embedder,
        source_type="player_document",
    )

    embedder.embed_query.assert_called_once_with("사건 기록")


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
    embedder,
    query,
    error_type,
):
    """잘못된 질문 입력을 차단한다."""

    with pytest.raises(error_type):
        search_dense_candidates(
            query,
            client=client,
            embedder=embedder,
            source_type="player_document",
        )

    embedder.embed_query.assert_not_called()


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
    embedder,
    top_k,
    error_type,
):
    """잘못된 검색 개수를 차단한다."""

    with pytest.raises(error_type):
        search_dense_candidates(
            "사건 기록",
            client=client,
            embedder=embedder,
            source_type="player_document",
            top_k=top_k,
        )


def test_invalid_source_type_rejected(client, embedder):
    """지원하지 않는 문서 유형을 차단한다."""

    with pytest.raises(
        ValueError,
        match="지원하지 않는 문서 유형",
    ):
        search_dense_candidates(
            "사건 기록",
            client=client,
            embedder=embedder,
            source_type="unknown",
        )


def test_npc_requires_character_id(client, embedder):
    """NPC 검색 시 인물 ID를 필수로 요구한다."""

    with pytest.raises(
        ValueError,
        match="character_id가 필요합니다",
    ):
        search_dense_candidates(
            "목격자 진술",
            client=client,
            embedder=embedder,
            source_type="npc_knowledge",
        )


def test_player_document_rejects_character_id(client, embedder):
    """플레이어 문서에 NPC ID를 지정할 수 없다."""

    with pytest.raises(
        ValueError,
        match="character_id를 지정할 수 없습니다",
    ):
        search_dense_candidates(
            "사건 기록",
            client=client,
            embedder=embedder,
            source_type="player_document",
            character_id="C01",
        )


def test_invalid_embedding_dimension(client, embedder):
    """1024차원이 아닌 질문 벡터는 거부한다."""

    embedder.embed_query.return_value = [0.1] * 768

    with pytest.raises(
        ValueError,
        match="임베딩 차원이 일치하지 않습니다",
    ):
        search_dense_candidates(
            "사건 기록",
            client=client,
            embedder=embedder,
            source_type="player_document",
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_finite_embedding_rejected(
    client,
    embedder,
    invalid_value,
):
    """NaN과 Infinity 질문 벡터를 거부한다."""

    embedder.embed_query.return_value = [invalid_value] * DENSE_VECTOR_SIZE

    with pytest.raises(
        ValueError,
        match="유효하지 않은 질문 임베딩",
    ):
        search_dense_candidates(
            "사건 기록",
            client=client,
            embedder=embedder,
            source_type="player_document",
        )


def test_zero_embedding_rejected(client, embedder):
    """영벡터 질문을 거부한다."""

    embedder.embed_query.return_value = [0.0] * DENSE_VECTOR_SIZE

    with pytest.raises(
        ValueError,
        match="영벡터",
    ):
        search_dense_candidates(
            "사건 기록",
            client=client,
            embedder=embedder,
            source_type="player_document",
        )
