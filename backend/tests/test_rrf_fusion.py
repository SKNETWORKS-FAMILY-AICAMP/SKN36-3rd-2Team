"""Dense + Sparse RRF 결합 단위 테스트."""

from dataclasses import asdict

import pytest

from crimescene.retriever.dense_search import DenseSearchCandidate
from crimescene.retriever.rrf_fusion import (
    HybridSearchCandidate,
    fuse_rrf_candidates,
)
from crimescene.retriever.sparse_search import SparseSearchCandidate


def dense(*point_ids):
    """테스트용 Dense 검색 결과 생성."""

    return [
        DenseSearchCandidate(
            point_id=point_id,
            score=1.0 - index * 0.1,
        )
        for index, point_id in enumerate(point_ids)
    ]


def sparse(*point_ids):
    """테스트용 Sparse 검색 결과 생성."""

    return [
        SparseSearchCandidate(
            point_id=point_id,
            score=10.0 - index,
        )
        for index, point_id in enumerate(point_ids)
    ]


def test_fuse_dense_and_sparse():
    """Dense와 Sparse 검색 결과를 하나로 결합한다."""

    results = fuse_rrf_candidates(
        dense("A", "B", "C"),
        sparse("B", "C", "D"),
    )

    assert len(results) == 4

    assert {item.point_id for item in results} == {"A", "B", "C", "D"}


def test_shared_candidate_gets_both_scores():
    """양쪽에 등장한 UUID는 RRF 점수를 누적한다."""

    results = fuse_rrf_candidates(
        dense("A", "B"),
        sparse("B", "C"),
    )

    scores = {item.point_id: item.score for item in results}

    expected_b = 1 / (60 + 2) + 1 / (60 + 1)

    assert scores["B"] == pytest.approx(expected_b)

    assert scores["B"] > scores["A"]
    assert scores["B"] > scores["C"]


def test_rrf_ranking():
    """RRF 점수가 높은 후보를 먼저 반환한다."""

    results = fuse_rrf_candidates(
        dense("A", "B", "C"),
        sparse("B", "C", "D"),
    )

    assert results[0].point_id == "B"
    assert results[1].point_id == "C"

    assert all(
        results[index].score >= results[index + 1].score
        for index in range(len(results) - 1)
    )


def test_default_rrf_k():
    """기본 RRF 상수는 60이다."""

    results = fuse_rrf_candidates(
        dense("A"),
        [],
    )

    assert results[0].score == pytest.approx(1 / 61)


def test_custom_rrf_k():
    """사용자가 지정한 RRF 상수를 적용한다."""

    results = fuse_rrf_candidates(
        dense("A"),
        sparse("A"),
        rrf_k=10,
    )

    assert results[0].score == pytest.approx(2 / 11)


def test_sparse_empty_fallback():
    """BM25 검색 결과가 없어도 Dense 결과를 유지한다."""

    results = fuse_rrf_candidates(
        dense("A", "B", "C"),
        [],
    )

    assert [item.point_id for item in results] == ["A", "B", "C"]


def test_dense_empty_fallback():
    """Dense 결과가 없어도 BM25 결과를 유지한다."""

    results = fuse_rrf_candidates(
        [],
        sparse("A", "B", "C"),
    )

    assert [item.point_id for item in results] == ["A", "B", "C"]


def test_both_empty():
    """검색 결과가 모두 없으면 빈 목록을 반환한다."""

    results = fuse_rrf_candidates([], [])

    assert results == []


def test_top_k_limit():
    """최종 반환 개수를 제한한다."""

    results = fuse_rrf_candidates(
        dense("A", "B", "C", "D"),
        sparse("B", "C", "D", "E"),
        top_k=2,
    )

    assert len(results) == 2


def test_tie_breaking_by_uuid():
    """RRF 점수가 같으면 UUID 문자열 순으로 정렬한다."""

    results = fuse_rrf_candidates(
        dense("B", "A"),
        sparse("A", "B"),
    )

    assert results[0].score == pytest.approx(results[1].score)

    assert [item.point_id for item in results] == ["A", "B"]


def test_candidate_type():
    """결합 결과는 HybridSearchCandidate 타입이다."""

    results = fuse_rrf_candidates(
        dense("A"),
        sparse("B"),
    )

    assert all(isinstance(item, HybridSearchCandidate) for item in results)


def test_candidate_contains_no_payload():
    """결과에는 UUID와 점수만 포함한다."""

    results = fuse_rrf_candidates(
        dense("A"),
        sparse("A"),
    )

    assert set(asdict(results[0])) == {
        "point_id",
        "score",
    }


def test_original_results_not_modified():
    """RRF 결합 과정에서 원본 검색 결과를 수정하지 않는다."""

    dense_results = dense("A", "B")
    sparse_results = sparse("B", "C")

    original_dense = dense_results.copy()
    original_sparse = sparse_results.copy()

    fuse_rrf_candidates(
        dense_results,
        sparse_results,
    )

    assert dense_results == original_dense
    assert sparse_results == original_sparse


def test_duplicate_dense_uuid_rejected():
    """Dense 결과 내부의 UUID 중복을 차단한다."""

    with pytest.raises(
        ValueError,
        match="중복된 검색 후보 UUID",
    ):
        fuse_rrf_candidates(
            dense("A", "A"),
            sparse("B"),
        )


def test_duplicate_sparse_uuid_rejected():
    """Sparse 결과 내부의 UUID 중복을 차단한다."""

    with pytest.raises(
        ValueError,
        match="중복된 검색 후보 UUID",
    ):
        fuse_rrf_candidates(
            dense("A"),
            sparse("B", "B"),
        )


def test_same_uuid_across_search_types_allowed():
    """Dense와 Sparse 사이의 동일 UUID는 정상 결합한다."""

    results = fuse_rrf_candidates(
        dense("A"),
        sparse("A"),
    )

    assert len(results) == 1
    assert results[0].point_id == "A"


@pytest.mark.parametrize(
    "invalid_input",
    [
        None,
        123,
        "invalid",
    ],
)
def test_invalid_dense_input_rejected(invalid_input):
    """잘못된 Dense 결과 목록을 차단한다."""

    with pytest.raises(TypeError):
        fuse_rrf_candidates(
            invalid_input,
            sparse("A"),
        )


@pytest.mark.parametrize(
    "invalid_input",
    [
        None,
        123,
        "invalid",
    ],
)
def test_invalid_sparse_input_rejected(invalid_input):
    """잘못된 Sparse 결과 목록을 차단한다."""

    with pytest.raises(TypeError):
        fuse_rrf_candidates(
            dense("A"),
            invalid_input,
        )


def test_invalid_dense_candidate_type():
    """Dense 후보 타입이 잘못되면 차단한다."""

    with pytest.raises(
        TypeError,
        match="검색 후보 타입",
    ):
        fuse_rrf_candidates(
            ["invalid"],
            [],
        )


def test_invalid_sparse_candidate_type():
    """Sparse 후보 타입이 잘못되면 차단한다."""

    with pytest.raises(
        TypeError,
        match="검색 후보 타입",
    ):
        fuse_rrf_candidates(
            [],
            ["invalid"],
        )


@pytest.mark.parametrize(
    "point_id",
    [
        "",
        None,
        123,
    ],
)
def test_invalid_point_id_rejected(point_id):
    """유효하지 않은 후보 ID를 차단한다."""

    candidate = DenseSearchCandidate(
        point_id=point_id,
        score=0.5,
    )

    with pytest.raises(
        ValueError,
        match="검색 후보 UUID",
    ):
        fuse_rrf_candidates(
            [candidate],
            [],
        )


@pytest.mark.parametrize(
    "invalid_score",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_invalid_dense_score_rejected(invalid_score):
    """비정상 Dense 점수를 차단한다."""

    candidate = DenseSearchCandidate(
        point_id="A",
        score=invalid_score,
    )

    with pytest.raises(
        ValueError,
        match="유효하지 않은 검색 점수",
    ):
        fuse_rrf_candidates(
            [candidate],
            [],
        )


@pytest.mark.parametrize(
    "invalid_score",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_invalid_sparse_score_rejected(invalid_score):
    """비정상 Sparse 점수를 차단한다."""

    candidate = SparseSearchCandidate(
        point_id="A",
        score=invalid_score,
    )

    with pytest.raises(
        ValueError,
        match="유효하지 않은 검색 점수",
    ):
        fuse_rrf_candidates(
            [],
            [candidate],
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
def test_invalid_top_k_rejected(top_k, error_type):
    """잘못된 최종 검색 개수를 차단한다."""

    with pytest.raises(error_type):
        fuse_rrf_candidates(
            dense("A"),
            sparse("B"),
            top_k=top_k,
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
def test_invalid_rrf_k_rejected(rrf_k, error_type):
    """잘못된 RRF 상수를 차단한다."""

    with pytest.raises(error_type):
        fuse_rrf_candidates(
            dense("A"),
            sparse("B"),
            rrf_k=rrf_k,
        )
