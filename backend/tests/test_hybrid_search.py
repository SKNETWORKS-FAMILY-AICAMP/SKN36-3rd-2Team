"""Dense + Sparse + RRF Hybrid Search 단위 테스트."""

from dataclasses import asdict
from unittest.mock import Mock

import pytest

from crimescene.retriever import hybrid_search
from crimescene.retriever.dense_search import DenseSearchCandidate
from crimescene.retriever.rrf_fusion import HybridSearchCandidate
from crimescene.retriever.sparse_search import SparseSearchCandidate


@pytest.fixture
def dependencies():
    """실제 서버를 호출하지 않는 테스트 의존성."""

    return {
        "client": object(),
        "embedder": object(),
        "encoder": object(),
    }


@pytest.fixture
def search_mocks(monkeypatch):
    """Dense와 Sparse 검색 함수를 Mock으로 교체."""

    dense_mock = Mock(
        return_value=[
            DenseSearchCandidate("A", 0.95),
            DenseSearchCandidate("B", 0.90),
            DenseSearchCandidate("C", 0.85),
        ]
    )

    sparse_mock = Mock(
        return_value=[
            SparseSearchCandidate("B", 5.0),
            SparseSearchCandidate("C", 4.0),
            SparseSearchCandidate("D", 3.0),
        ]
    )

    monkeypatch.setattr(
        hybrid_search,
        "search_dense_candidates",
        dense_mock,
    )

    monkeypatch.setattr(
        hybrid_search,
        "search_sparse_candidates",
        sparse_mock,
    )

    return dense_mock, sparse_mock


def run_search(dependencies, **overrides):
    """기본 설정으로 Hybrid Search 호출."""

    params = {
        **dependencies,
        "source_type": "player_document",
        **overrides,
    }

    return hybrid_search.search_hybrid_candidates(
        "신기범 학교 출입 기록",
        **params,
    )


def test_dense_and_sparse_called(dependencies, search_mocks):
    """두 검색 함수가 모두 호출된다."""

    dense_mock, sparse_mock = search_mocks

    results = run_search(dependencies)

    dense_mock.assert_called_once()
    sparse_mock.assert_called_once()

    assert results


def test_rrf_combines_results(dependencies, search_mocks):
    """Dense와 Sparse 후보를 중복 없이 결합한다."""

    results = run_search(dependencies)

    assert len(results) == 4

    assert {item.point_id for item in results} == {"A", "B", "C", "D"}


def test_rrf_ranking(dependencies, search_mocks):
    """양쪽에서 상위 검색된 문서가 우선한다."""

    results = run_search(dependencies)

    assert [item.point_id for item in results] == ["B", "C", "A", "D"]

    assert all(
        results[i].score >= results[i + 1].score for i in range(len(results) - 1)
    )


def test_shared_uuid_score_accumulation(
    dependencies,
    search_mocks,
):
    """공통 UUID에 두 검색 방식의 RRF 점수를 누적한다."""

    results = run_search(dependencies)

    scores = {item.point_id: item.score for item in results}

    assert scores["B"] == pytest.approx(1 / 62 + 1 / 61)

    assert scores["B"] > scores["A"]


def test_query_trimmed(dependencies, search_mocks):
    """두 검색 함수에 공백 제거된 질문을 전달한다."""

    dense_mock, sparse_mock = search_mocks

    run_search(dependencies)

    assert dense_mock.call_args.args[0] == ("신기범 학교 출입 기록")

    assert sparse_mock.call_args.args[0] == ("신기범 학교 출입 기록")


def test_identical_filters_forwarded(
    dependencies,
    search_mocks,
):
    """Dense와 Sparse에 동일한 검색 조건을 전달한다."""

    dense_mock, sparse_mock = search_mocks

    run_search(
        dependencies,
        case_id="CASE-001",
        collection_name="case001_rag_v1",
        candidate_k=20,
    )

    dense_kwargs = dense_mock.call_args.kwargs
    sparse_kwargs = sparse_mock.call_args.kwargs

    for key in (
        "source_type",
        "case_id",
        "character_id",
        "top_k",
        "collection_name",
    ):
        assert dense_kwargs[key] == sparse_kwargs[key]

    assert dense_kwargs["source_type"] == "player_document"
    assert dense_kwargs["top_k"] == 20
    assert dense_kwargs["character_id"] is None


def test_dependencies_forwarded(
    dependencies,
    search_mocks,
):
    """각 검색 함수에 올바른 클라이언트를 전달한다."""

    dense_mock, sparse_mock = search_mocks

    run_search(dependencies)

    assert dense_mock.call_args.kwargs["client"] is dependencies["client"]

    assert dense_mock.call_args.kwargs["embedder"] is dependencies["embedder"]

    assert sparse_mock.call_args.kwargs["encoder"] is dependencies["encoder"]


def test_npc_character_filter(
    dependencies,
    search_mocks,
):
    """NPC 검색 시 인물 ID를 두 검색 함수에 전달한다."""

    dense_mock, sparse_mock = search_mocks

    run_search(
        dependencies,
        source_type="npc_knowledge",
        character_id="C01",
    )

    for mock in (dense_mock, sparse_mock):
        kwargs = mock.call_args.kwargs

        assert kwargs["source_type"] == "npc_knowledge"
        assert kwargs["character_id"] == "C01"


def test_top_k_limit(dependencies, search_mocks):
    """최종 결과 개수는 top_k를 초과하지 않는다."""

    results = run_search(
        dependencies,
        candidate_k=5,
        top_k=2,
    )

    assert len(results) == 2
    assert [item.point_id for item in results] == ["B", "C"]


def test_custom_rrf_k(dependencies, search_mocks):
    """사용자가 지정한 RRF 상수를 적용한다."""

    results = run_search(
        dependencies,
        rrf_k=10,
    )

    scores = {item.point_id: item.score for item in results}

    assert scores["B"] == pytest.approx(1 / 12 + 1 / 11)


def test_sparse_empty_fallback(
    dependencies,
    search_mocks,
):
    """BM25 결과가 0건이어도 Dense 결과를 반환한다."""

    _, sparse_mock = search_mocks

    sparse_mock.return_value = []

    results = run_search(dependencies)

    assert [item.point_id for item in results] == ["A", "B", "C"]


def test_dense_empty_fallback(
    dependencies,
    search_mocks,
):
    """Dense 결과가 없으면 Sparse 결과만 반환한다."""

    dense_mock, _ = search_mocks

    dense_mock.return_value = []

    results = run_search(dependencies)

    assert [item.point_id for item in results] == ["B", "C", "D"]


def test_both_empty(dependencies, search_mocks):
    """두 검색 결과가 모두 없으면 빈 목록을 반환한다."""

    dense_mock, sparse_mock = search_mocks

    dense_mock.return_value = []
    sparse_mock.return_value = []

    assert run_search(dependencies) == []


def test_candidate_type(dependencies, search_mocks):
    """결과는 HybridSearchCandidate 타입이다."""

    results = run_search(dependencies)

    assert all(isinstance(item, HybridSearchCandidate) for item in results)


def test_no_document_payload(dependencies, search_mocks):
    """최종 후보에는 본문과 접근 정책 정보가 없다."""

    results = run_search(dependencies)

    for item in results:
        assert set(asdict(item)) == {
            "point_id",
            "score",
        }


def test_dense_error_propagated(
    dependencies,
    search_mocks,
):
    """Dense 검색 오류를 숨기지 않고 전달한다."""

    dense_mock, sparse_mock = search_mocks

    dense_mock.side_effect = RuntimeError("Ollama unavailable")

    with pytest.raises(
        RuntimeError,
        match="Ollama unavailable",
    ):
        run_search(dependencies)

    sparse_mock.assert_not_called()


def test_sparse_error_propagated(
    dependencies,
    search_mocks,
):
    """Sparse 검색 오류를 숨기지 않고 전달한다."""

    _, sparse_mock = search_mocks

    sparse_mock.side_effect = RuntimeError("Qdrant sparse search failed")

    with pytest.raises(
        RuntimeError,
        match="Qdrant sparse search failed",
    ):
        run_search(dependencies)


def test_sparse_keyword_error_propagated(
    dependencies,
    search_mocks,
):
    """키워드 추출 실패는 현재 구현에서 예외로 처리한다."""

    _, sparse_mock = search_mocks

    sparse_mock.side_effect = ValueError("검색에 사용할 키워드를 추출하지 못했습니다.")

    with pytest.raises(ValueError):
        run_search(dependencies)


@pytest.mark.parametrize(
    ("query", "error_type"),
    [
        ("", ValueError),
        ("   ", ValueError),
        (None, TypeError),
        (123, TypeError),
    ],
)
def test_invalid_query(
    dependencies,
    search_mocks,
    query,
    error_type,
):
    """유효하지 않은 질문을 차단한다."""

    with pytest.raises(error_type):
        hybrid_search.search_hybrid_candidates(
            query,
            **dependencies,
            source_type="player_document",
        )

    search_mocks[0].assert_not_called()
    search_mocks[1].assert_not_called()


@pytest.mark.parametrize(
    "source_type",
    ["unknown", "", None],
)
def test_invalid_source_type(
    dependencies,
    search_mocks,
    source_type,
):
    """지원하지 않는 문서 유형을 차단한다."""

    with pytest.raises(ValueError):
        run_search(
            dependencies,
            source_type=source_type,
        )


def test_npc_requires_character_id(
    dependencies,
    search_mocks,
):
    """NPC 지식 검색에는 인물 ID가 필요하다."""

    with pytest.raises(
        ValueError,
        match="character_id",
    ):
        run_search(
            dependencies,
            source_type="npc_knowledge",
        )


def test_player_document_rejects_character_id(
    dependencies,
    search_mocks,
):
    """플레이어 문서 검색에 NPC ID를 지정할 수 없다."""

    with pytest.raises(
        ValueError,
        match="character_id",
    ):
        run_search(
            dependencies,
            character_id="C01",
        )


@pytest.mark.parametrize(
    "case_id",
    ["", "   ", None],
)
def test_invalid_case_id(
    dependencies,
    search_mocks,
    case_id,
):
    """유효하지 않은 사건 ID를 차단한다."""

    with pytest.raises(
        ValueError,
        match="사건 ID",
    ):
        run_search(
            dependencies,
            case_id=case_id,
        )


@pytest.mark.parametrize(
    "collection_name",
    ["", "   ", None],
)
def test_invalid_collection_name(
    dependencies,
    search_mocks,
    collection_name,
):
    """유효하지 않은 컬렉션 이름을 차단한다."""

    with pytest.raises(
        ValueError,
        match="컬렉션 이름",
    ):
        run_search(
            dependencies,
            collection_name=collection_name,
        )


@pytest.mark.parametrize(
    ("candidate_k", "error_type"),
    [
        (0, ValueError),
        (-1, ValueError),
        (101, ValueError),
        (True, TypeError),
        ("10", TypeError),
    ],
)
def test_invalid_candidate_k(
    dependencies,
    search_mocks,
    candidate_k,
    error_type,
):
    """잘못된 후보 검색 개수를 차단한다."""

    with pytest.raises(error_type):
        run_search(
            dependencies,
            candidate_k=candidate_k,
        )


@pytest.mark.parametrize(
    ("top_k", "error_type"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        ("10", TypeError),
    ],
)
def test_invalid_top_k(
    dependencies,
    search_mocks,
    top_k,
    error_type,
):
    """잘못된 최종 반환 개수를 차단한다."""

    with pytest.raises(error_type):
        run_search(
            dependencies,
            top_k=top_k,
        )


def test_top_k_exceeds_candidate_k(
    dependencies,
    search_mocks,
):
    """최종 반환 개수가 후보 검색 개수보다 클 수 없다."""

    with pytest.raises(
        ValueError,
        match="candidate_k",
    ):
        run_search(
            dependencies,
            candidate_k=5,
            top_k=10,
        )


@pytest.mark.parametrize(
    ("rrf_k", "error_type"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        ("60", TypeError),
    ],
)
def test_invalid_rrf_k(
    dependencies,
    search_mocks,
    rrf_k,
    error_type,
):
    """잘못된 RRF 상수를 차단한다."""

    with pytest.raises(error_type):
        run_search(
            dependencies,
            rrf_k=rrf_k,
        )
