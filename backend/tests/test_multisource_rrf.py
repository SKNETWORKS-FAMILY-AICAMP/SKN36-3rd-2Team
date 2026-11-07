"""Dense + BM25 + Graph 3중 RRF 테스트."""

from dataclasses import asdict

import pytest

from crimescene.retriever.dense_search import DenseSearchCandidate
from crimescene.retriever.graph_evidence_search import EvidenceGraphResult
from crimescene.retriever.graph_search import GraphSearchResult
from crimescene.retriever.multisource_rrf import (
    FusedSearchCandidate,
    fuse_multisource_candidates,
)
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.retriever.sparse_search import SparseSearchCandidate


def dense(*ids):
    return [
        DenseSearchCandidate(
            point_id=item_id,
            score=1.0 - index * 0.1,
        )
        for index, item_id in enumerate(ids)
    ]


def bm25(*ids):
    return [
        SparseSearchCandidate(
            point_id=item_id,
            score=10.0 - index,
        )
        for index, item_id in enumerate(ids)
    ]


def relation(edge_id="REL-001"):
    return GraphSearchResult(
        edge_id=edge_id,
        source_id="C01",
        target_id="C02",
        neighbor_id="C02",
        relation="KNOWS",
        truth_status="documented",
        access_scope="public",
        incident_year=2026,
    )


def graph(
    *,
    relations=(),
    evidence=(),
):
    return QuestionGraphContext(
        character_id="C01",
        matched_entity_ids=("C02",),
        relations=tuple(relations),
        evidence=tuple(evidence),
    )


def test_three_way_fusion():
    """Dense, BM25, Graph 결과를 하나로 통합한다."""

    result = fuse_multisource_candidates(
        dense("A", "B"),
        bm25("B", "C"),
        graph(
            relations=[relation()],
        ),
    )

    keys = {(item.kind, item.item_id) for item in result}

    assert keys == {
        ("chunk", "A"),
        ("chunk", "B"),
        ("chunk", "C"),
        ("relation", "REL-001"),
    }


def test_shared_document_rrf_score():
    """Dense와 BM25에 공통으로 등장한 문서의 점수를 합산한다."""

    result = fuse_multisource_candidates(
        dense("A", "B"),
        bm25("B", "C"),
        graph(),
    )

    scores = {item.item_id: item.score for item in result}

    expected = 1 / (60 + 2) + 1 / (60 + 1)

    assert scores["B"] == pytest.approx(expected)

    assert result[0].item_id == "B"


def test_graph_relation_included():
    """Neo4j 관계를 통합 검색 후보에 포함한다."""

    result = fuse_multisource_candidates(
        [],
        [],
        graph(relations=[relation("REL-001")]),
    )

    assert len(result) == 1

    assert result[0].kind == "relation"
    assert result[0].item_id == "REL-001"
    assert result[0].methods == ("graph",)


def test_graph_evidence_included():
    """Neo4j 증거도 검색 후보에 포함한다."""

    result = fuse_multisource_candidates(
        [],
        [],
        graph(
            evidence=[
                EvidenceGraphResult(
                    evidence_id="E01",
                    holder_id="C01",
                )
            ]
        ),
    )

    assert len(result) == 1

    assert result[0].kind == "evidence"
    assert result[0].item_id == "E01"


def test_cross_method_duplicate_removed():
    """동일한 문서 UUID는 하나의 결과로 통합한다."""

    result = fuse_multisource_candidates(
        dense("UUID-001"),
        bm25("UUID-001"),
        graph(),
    )

    assert len(result) == 1

    assert result[0].methods == (
        "dense",
        "bm25",
    )


def test_different_kinds_not_merged():
    """문서 UUID와 관계 ID가 같더라도 잘못 합치지 않는다."""

    result = fuse_multisource_candidates(
        dense("REL-001"),
        [],
        graph(relations=[relation("REL-001")]),
    )

    assert len(result) == 2

    assert {item.kind for item in result} == {
        "chunk",
        "relation",
    }


def test_ranking_order():
    """RRF 점수가 높은 후보를 상위에 배치한다."""

    result = fuse_multisource_candidates(
        dense("A", "B", "C"),
        bm25("B", "C", "D"),
        graph(relations=[relation()]),
    )

    assert result[0].item_id == "B"
    assert result[1].item_id == "C"

    assert all(
        result[index].score >= result[index + 1].score
        for index in range(len(result) - 1)
    )


def test_top_k_limit():
    """최종 검색 후보 개수를 제한한다."""

    result = fuse_multisource_candidates(
        dense("A", "B", "C"),
        bm25("B", "C", "D"),
        graph(relations=[relation()]),
        top_k=2,
    )

    assert len(result) == 2


def test_default_returns_all_candidates():
    """기본 설정에서는 권한 검사 전 후보를 자르지 않는다."""

    result = fuse_multisource_candidates(
        dense("A", "B", "C"),
        bm25("D", "E", "F"),
        graph(relations=[relation()]),
    )

    assert len(result) == 7


def test_empty_results():
    """모든 검색 결과가 비어 있으면 빈 목록을 반환한다."""

    result = fuse_multisource_candidates(
        [],
        [],
        graph(),
    )

    assert result == []


def test_no_payload_exposure():
    """통합 후보에는 문서 본문이나 비공개 메타데이터를 포함하지 않는다."""

    result = fuse_multisource_candidates(
        dense("A"),
        bm25("A"),
        graph(),
    )

    assert isinstance(result[0], FusedSearchCandidate)

    assert set(asdict(result[0])) == {
        "kind",
        "item_id",
        "score",
        "methods",
    }


def test_duplicate_dense_rejected():
    """동일 검색 방식 내부의 UUID 중복을 차단한다."""

    with pytest.raises(ValueError, match="중복"):
        fuse_multisource_candidates(
            dense("A", "A"),
            [],
            graph(),
        )


def test_duplicate_graph_relation_rejected():
    """Neo4j 관계 ID 중복을 차단한다."""

    with pytest.raises(ValueError, match="중복"):
        fuse_multisource_candidates(
            [],
            [],
            graph(
                relations=[
                    relation("REL-001"),
                    relation("REL-001"),
                ],
            ),
        )


@pytest.mark.parametrize(
    "score",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_invalid_vector_score_rejected(score):
    """비정상 검색 점수는 결합하지 않는다."""

    candidates = [
        DenseSearchCandidate(
            point_id="A",
            score=score,
        )
    ]

    with pytest.raises(ValueError, match="검색 점수"):
        fuse_multisource_candidates(
            candidates,
            [],
            graph(),
        )


@pytest.mark.parametrize(
    "top_k",
    [
        0,
        301,
    ],
)
def test_invalid_top_k_value(top_k):
    """잘못된 Top-K 범위를 거부한다."""

    with pytest.raises(ValueError, match="top_k"):
        fuse_multisource_candidates(
            dense("A"),
            [],
            graph(),
            top_k=top_k,
        )


def test_invalid_top_k_type():
    """Top-K 자료형 오류를 거부한다."""

    with pytest.raises(TypeError, match="top_k"):
        fuse_multisource_candidates(
            dense("A"),
            [],
            graph(),
            top_k=True,
        )


def test_invalid_graph_type():
    """Graph Retrieval 결과 모델을 검증한다."""

    with pytest.raises(TypeError, match="QuestionGraphContext"):
        fuse_multisource_candidates(
            dense("A"),
            bm25("B"),
            None,
        )


def test_custom_rrf_k():
    """RRF 보정 상수를 변경할 수 있다."""

    result = fuse_multisource_candidates(
        dense("A"),
        bm25("A"),
        graph(),
        rrf_k=10,
    )

    assert result[0].score == pytest.approx(2 / 11)
