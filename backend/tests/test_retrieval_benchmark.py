"""CASE-001 검색 벤치마크 검증."""

import csv
from unittest.mock import Mock

import pytest

from crimescene.retriever.dense_search import DenseSearchCandidate
from crimescene.retriever.retrieval_benchmark import (
    ReviewQuestion,
    evaluate_questions,
    load_review_questions,
)
from crimescene.retriever.rrf_fusion import HybridSearchCandidate
from crimescene.retriever.search_comparison import SearchComparisonResult
from crimescene.retriever.sparse_search import SparseSearchCandidate


def write_review(tmp_path, rows):
    path = tmp_path / "review.csv"

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "question_id",
                "question",
                "point_id",
                "relevant",
            ],
        )

        writer.writeheader()
        writer.writerows(rows)

    return path


def valid_rows():
    return [
        {
            "question_id": "Q001",
            "question": "테스트 질문",
            "point_id": "A",
            "relevant": "1",
        },
        {
            "question_id": "Q001",
            "question": "테스트 질문",
            "point_id": "B",
            "relevant": "0",
        },
    ]


def test_load_review(tmp_path):
    path = write_review(tmp_path, valid_rows())

    cases = load_review_questions(
        path,
        trusted_point_ids={"A", "B"},
    )

    assert len(cases) == 1
    assert cases[0].relevant_point_ids == ("A",)


def test_missing_label_rejected(tmp_path):
    rows = valid_rows()
    rows[0]["relevant"] = ""

    path = write_review(tmp_path, rows)

    with pytest.raises(ValueError, match="relevant"):
        load_review_questions(
            path,
            trusted_point_ids={"A", "B"},
        )


def test_incomplete_review_rejected(tmp_path):
    path = write_review(
        tmp_path,
        valid_rows()[:1],
    )

    with pytest.raises(ValueError, match="평가하지 않은"):
        load_review_questions(
            path,
            trusted_point_ids={"A", "B"},
        )


def test_unknown_uuid_rejected(tmp_path):
    rows = valid_rows()
    rows[1]["point_id"] = "UNKNOWN"

    path = write_review(tmp_path, rows)

    with pytest.raises(ValueError, match="신뢰 원본"):
        load_review_questions(
            path,
            trusted_point_ids={"A", "B"},
        )


def test_duplicate_uuid_rejected(tmp_path):
    rows = valid_rows()
    rows[1]["point_id"] = "A"

    path = write_review(tmp_path, rows)

    with pytest.raises(ValueError, match="중복 UUID"):
        load_review_questions(
            path,
            trusted_point_ids={"A", "B"},
        )


def test_metrics_aggregated():
    question = ReviewQuestion(
        question_id="Q001",
        question="테스트 질문",
        relevant_point_ids=("A",),
    )

    search_result = SearchComparisonResult(
        query="테스트 질문",
        dense=(
            DenseSearchCandidate("A", 0.9),
            DenseSearchCandidate("B", 0.8),
        ),
        sparse=(
            SparseSearchCandidate("B", 2.0),
            SparseSearchCandidate("A", 1.0),
        ),
        hybrid=(
            HybridSearchCandidate("A", 0.03),
            HybridSearchCandidate("B", 0.02),
        ),
    )

    search_fn = Mock(return_value=search_result)

    details, averages = evaluate_questions(
        [question],
        search_fn,
    )

    assert len(details) == 1
    assert averages["dense"]["mrr_at_10"] == 1.0
    assert averages["bm25"]["mrr_at_10"] == 0.5
    assert averages["hybrid"]["mrr_at_10"] == 1.0

    search_fn.assert_called_once_with("테스트 질문")


def test_empty_questions_rejected():
    with pytest.raises(ValueError, match="평가 질문"):
        evaluate_questions([], Mock())
