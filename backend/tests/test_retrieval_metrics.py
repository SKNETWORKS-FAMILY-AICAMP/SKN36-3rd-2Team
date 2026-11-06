"""검색 정확도 평가 지표 테스트."""

from math import isclose, log2

import pytest

from crimescene.retriever.retrieval_metrics import (
    aggregate_retrieval_metrics,
    evaluate_retrieval_ranking,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
)


def test_perfect_retrieval():
    """정답을 모두 상위에서 검색한 경우."""

    result = evaluate_retrieval_ranking(
        ["A", "B", "X"],
        ["A", "B"],
    )

    assert result == {
        "recall_at_5": 1.0,
        "recall_at_10": 1.0,
        "mrr_at_10": 1.0,
        "ndcg_at_10": 1.0,
    }


def test_retrieval_with_wrong_document_between():
    """정답 사이에 오답이 있으면 nDCG가 감소한다."""

    result = evaluate_retrieval_ranking(
        ["A", "X", "B"],
        ["A", "B"],
    )

    assert result["recall_at_5"] == 1.0
    assert result["recall_at_10"] == 1.0
    assert result["mrr_at_10"] == 1.0

    assert isclose(
        result["ndcg_at_10"],
        0.9197207891481876,
    )


def test_no_relevant_document_retrieved():
    """정답 문서를 검색하지 못하면 모든 점수가 0이다."""

    result = evaluate_retrieval_ranking(
        ["X", "Y", "Z"],
        ["A", "B"],
    )

    assert all(value == 0.0 for value in result.values())


def test_empty_retrieval_result():
    """검색 결과가 비어 있어도 정상적으로 점수를 계산한다."""

    result = evaluate_retrieval_ranking(
        [],
        ["A"],
    )

    assert all(value == 0.0 for value in result.values())


def test_relevant_document_at_rank_six():
    """6위에 정답이 있으면 Recall@5는 0이다."""

    result = evaluate_retrieval_ranking(
        ["X1", "X2", "X3", "X4", "X5", "A"],
        ["A"],
    )

    assert result["recall_at_5"] == 0.0
    assert result["recall_at_10"] == 1.0

    assert isclose(
        result["mrr_at_10"],
        1 / 6,
    )

    assert isclose(
        result["ndcg_at_10"],
        1 / log2(7),
    )


def test_multiple_relevant_documents():
    """두 정답 중 하나만 검색한 경우."""

    result = evaluate_retrieval_ranking(
        ["A", "X", "Y"],
        ["A", "B"],
    )

    assert result["recall_at_5"] == 0.5
    assert result["recall_at_10"] == 0.5
    assert result["mrr_at_10"] == 1.0

    assert 0.0 < result["ndcg_at_10"] < 1.0


def test_duplicate_retrieved_ids():
    """검색 결과에 중복 UUID가 있어도 한 번만 계산한다."""

    result = evaluate_retrieval_ranking(
        ["A", "A", "B"],
        ["A", "B"],
    )

    assert result["recall_at_5"] == 1.0
    assert result["mrr_at_10"] == 1.0
    assert result["ndcg_at_10"] == 1.0


def test_empty_relevant_ids_rejected():
    """정답이 없는 평가 문제는 허용하지 않는다."""

    with pytest.raises(ValueError):
        evaluate_retrieval_ranking(
            ["A", "B"],
            [],
        )


@pytest.mark.parametrize(
    "invalid_ids",
    [
        [""],
        [" "],
        [None],
        [123],
    ],
)
def test_invalid_relevant_ids_rejected(invalid_ids):
    """잘못된 정답 UUID를 거부한다."""

    with pytest.raises(ValueError):
        evaluate_retrieval_ranking(
            ["A"],
            invalid_ids,
        )


@pytest.mark.parametrize(
    "invalid_ids",
    [
        [""],
        [" "],
        [None],
        [123],
    ],
)
def test_invalid_retrieved_ids_rejected(invalid_ids):
    """잘못된 검색 결과 UUID를 거부한다."""

    with pytest.raises(ValueError):
        evaluate_retrieval_ranking(
            invalid_ids,
            ["A"],
        )


@pytest.mark.parametrize(
    "metric_function",
    [
        recall_at_k,
        mrr_at_k,
        ndcg_at_k,
    ],
)
@pytest.mark.parametrize("k", [0, -1])
def test_invalid_k_rejected(metric_function, k):
    """K는 반드시 1 이상이어야 한다."""

    with pytest.raises(ValueError):
        metric_function(
            ["A"],
            {"A"},
            k,
        )


def test_aggregate_metrics():
    """여러 평가 질문의 평균을 계산한다."""

    rows = [
        {
            "recall_at_5": 1.0,
            "recall_at_10": 1.0,
            "mrr_at_10": 1.0,
            "ndcg_at_10": 1.0,
        },
        {
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "mrr_at_10": 0.0,
            "ndcg_at_10": 0.0,
        },
    ]

    result = aggregate_retrieval_metrics(rows)

    assert result == {
        "recall_at_5": 0.5,
        "recall_at_10": 0.5,
        "mrr_at_10": 0.5,
        "ndcg_at_10": 0.5,
    }


def test_aggregate_empty_rows_rejected():
    """평가 결과가 없으면 평균을 계산할 수 없다."""

    with pytest.raises(ValueError):
        aggregate_retrieval_metrics([])


def test_aggregate_missing_metric_rejected():
    """필수 평가 지표가 누락되면 오류를 발생시킨다."""

    with pytest.raises(ValueError):
        aggregate_retrieval_metrics(
            [{"recall_at_5": 1.0}],
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        -0.1,
        1.1,
        float("nan"),
        float("inf"),
        True,
    ],
)
def test_aggregate_invalid_score_rejected(invalid_value):
    """평가 점수는 유효한 0~1 실수여야 한다."""

    row = {
        "recall_at_5": invalid_value,
        "recall_at_10": 1.0,
        "mrr_at_10": 1.0,
        "ndcg_at_10": 1.0,
    }

    with pytest.raises(ValueError):
        aggregate_retrieval_metrics([row])
