"""Dense / BM25 / Hybrid 검색 결과 비교 테스트."""

from dataclasses import asdict
from unittest.mock import Mock

import pytest

import crimescene.retriever.search_comparison as comparison
from crimescene.retriever.dense_search import DenseSearchCandidate
from crimescene.retriever.sparse_search import SparseSearchCandidate


@pytest.fixture
def search_mocks(monkeypatch):
    """외부 DB 호출을 Mock으로 대체한다."""

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
            SparseSearchCandidate("D", 4.0),
            SparseSearchCandidate("C", 3.0),
        ]
    )

    monkeypatch.setattr(
        comparison,
        "search_dense_candidates",
        dense_mock,
    )

    monkeypatch.setattr(
        comparison,
        "search_sparse_candidates",
        sparse_mock,
    )

    return dense_mock, sparse_mock


def run_comparison(**kwargs):
    """테스트용 검색 비교 실행."""

    return comparison.compare_search_methods(
        "신기범 학교 출입 기록",
        client=object(),
        embedder=object(),
        encoder=object(),
        **kwargs,
    )


def test_both_search_methods_called(search_mocks):
    """Dense와 BM25가 각각 한 번 실행된다."""

    dense_mock, sparse_mock = search_mocks

    run_comparison()

    dense_mock.assert_called_once()
    sparse_mock.assert_called_once()


def test_dense_ranking_preserved(search_mocks):
    """Dense 검색 순위를 유지한다."""

    result = run_comparison()

    assert [item.point_id for item in result.dense] == [
        "A",
        "B",
        "C",
    ]


def test_bm25_ranking_preserved(search_mocks):
    """BM25 검색 순위를 유지한다."""

    result = run_comparison()

    assert [item.point_id for item in result.sparse] == [
        "B",
        "D",
        "C",
    ]


def test_hybrid_rrf_ranking(search_mocks):
    """공통 검색 후보가 RRF에서 높은 순위에 배치된다."""

    result = run_comparison()

    assert [item.point_id for item in result.hybrid] == [
        "B",
        "C",
        "A",
        "D",
    ]


def test_overlap_calculation(search_mocks):
    """두 검색 방식의 공통 후보를 계산한다."""

    result = run_comparison()

    assert result.overlap_ids == ("B", "C")
    assert result.overlap_count == 2


def test_top_k_limit(search_mocks):
    """비교 결과마다 최종 Top-K를 적용한다."""

    result = run_comparison(
        candidate_k=3,
        top_k=2,
    )

    assert len(result.dense) == 2
    assert len(result.sparse) == 2
    assert len(result.hybrid) == 2


def test_query_normalization(search_mocks):
    """질문 앞뒤 공백을 제거한다."""

    dense_mock, sparse_mock = search_mocks

    result = comparison.compare_search_methods(
        "  신기범 학교 기록  ",
        client=object(),
        embedder=object(),
        encoder=object(),
    )

    assert result.query == "신기범 학교 기록"

    assert dense_mock.call_args.args[0] == result.query
    assert sparse_mock.call_args.args[0] == result.query


def test_identical_search_filters(search_mocks):
    """두 검색 방식에 동일한 필터를 전달한다."""

    dense_mock, sparse_mock = search_mocks

    run_comparison(
        candidate_k=20,
        top_k=5,
        source_type="npc_knowledge",
        character_id="C01",
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

    assert dense_kwargs["character_id"] == "C01"
    assert dense_kwargs["top_k"] == 20


def test_sparse_empty_fallback(search_mocks):
    """BM25 검색 결과가 없어도 Dense 기반 결과를 유지한다."""

    _, sparse_mock = search_mocks
    sparse_mock.return_value = []

    result = run_comparison()

    assert result.sparse == ()
    assert len(result.dense) == 3
    assert len(result.hybrid) == 3


def test_search_candidates_do_not_expose_body(search_mocks):
    """검색 후보에 비공개 본문이 포함되지 않는다."""

    result = run_comparison()

    for candidate in (
        *result.dense,
        *result.sparse,
        *result.hybrid,
    ):
        assert set(asdict(candidate)) == {
            "point_id",
            "score",
        }


def test_evaluation_metrics(search_mocks):
    """정답 UUID를 기준으로 검색 품질을 평가한다."""

    result = run_comparison()

    metrics = comparison.evaluate_search_comparison(
        result,
        relevant_point_ids=["A"],
    )

    assert set(metrics) == {
        "dense",
        "bm25",
        "hybrid",
    }

    assert metrics["dense"]["mrr_at_10"] == 1.0
    assert metrics["hybrid"]["mrr_at_10"] == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    "invalid_top_k",
    [0, -1, 101, True, "5"],
)
def test_invalid_top_k_rejected(
    search_mocks,
    invalid_top_k,
):
    """잘못된 Top-K를 차단한다."""

    with pytest.raises(ValueError):
        run_comparison(top_k=invalid_top_k)


def test_empty_query_rejected(search_mocks):
    """빈 질문을 허용하지 않는다."""

    with pytest.raises(ValueError, match="비어 있습니다"):
        comparison.compare_search_methods(
            "   ",
            client=object(),
            embedder=object(),
            encoder=object(),
        )
