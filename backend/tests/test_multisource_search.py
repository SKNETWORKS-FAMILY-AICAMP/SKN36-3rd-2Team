"""CASE-001 Qdrant + Neo4j 통합 검색 테스트."""

from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

import crimescene.retriever.multisource_search as module
from crimescene.retriever.dense_search import DenseSearchCandidate
from crimescene.retriever.graph_search import GraphSearchResult
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.retriever.sparse_search import SparseSearchCandidate
from crimescene.scenario.schemas.game_state import GameState


@pytest.fixture
def registry():
    return [
        {
            "case_id": "CASE-001",
            "entity_id": "C01",
            "type": "Person",
            "label": "김서연",
        },
        {
            "case_id": "CASE-001",
            "entity_id": "C02",
            "type": "Person",
            "label": "박민수",
        },
        {
            "case_id": "CASE-001",
            "entity_id": "SERIN_SCHOOL",
            "type": "Institution",
            "label": "세린국제학교",
        },
    ]


def make_state(*, unlocked=None):
    return GameState(
        case_id="CASE-001",
        session_id="MULTISOURCE-TEST",
        unlocked_characters=(["C01"] if unlocked is None else unlocked),
        evidence={},
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


def make_graph():
    return QuestionGraphContext(
        character_id="C01",
        matched_entity_ids=("SERIN_SCHOOL",),
        relations=(
            GraphSearchResult(
                edge_id="REL-001",
                source_id="C01",
                target_id="SERIN_SCHOOL",
                neighbor_id="SERIN_SCHOOL",
                relation="VISITED",
                truth_status="documented",
                access_scope="public",
                incident_year=2026,
            ),
        ),
        evidence=(),
    )


@pytest.fixture
def searches(monkeypatch):
    graph_search = MagicMock(return_value=make_graph())

    dense_search = MagicMock(
        return_value=[
            DenseSearchCandidate("A", 0.9),
            DenseSearchCandidate("B", 0.8),
        ]
    )

    sparse_search = MagicMock(
        return_value=[
            SparseSearchCandidate("B", 2.0),
            SparseSearchCandidate("C", 1.0),
        ]
    )

    monkeypatch.setattr(
        module,
        "retrieve_question_graph",
        graph_search,
    )

    monkeypatch.setattr(
        module,
        "search_dense_candidates",
        dense_search,
    )

    monkeypatch.setattr(
        module,
        "search_sparse_candidates",
        sparse_search,
    )

    return graph_search, dense_search, sparse_search


def run_search(registry, **kwargs):
    return module.search_multisource_candidates(
        kwargs.pop(
            "query",
            "세린국제학교에서 무슨 일이 있었나요?",
        ),
        qdrant_client=MagicMock(),
        neo4j_driver=MagicMock(),
        embedder=MagicMock(),
        encoder=MagicMock(),
        state=kwargs.pop("state", make_state()),
        active_character_id=kwargs.pop(
            "active_character_id",
            "C01",
        ),
        registry=registry,
        trusted_edges=[],
        evidence_rules={},
        trusted_point_ids=kwargs.pop(
            "trusted_point_ids",
            {"A", "B", "C"},
        ),
        allowed_entity_ids=kwargs.pop(
            "allowed_entity_ids",
            {"SERIN_SCHOOL"},
        ),
        **kwargs,
    )


def test_three_search_engines_integrated(registry, searches):
    """Dense, BM25, Graph 세 검색 엔진을 호출한다."""

    graph_search, dense_search, sparse_search = searches

    result = run_search(registry)

    keys = {(item.kind, item.item_id) for item in result}

    assert keys == {
        ("chunk", "A"),
        ("chunk", "B"),
        ("chunk", "C"),
        ("relation", "REL-001"),
    }

    graph_search.assert_called_once()
    dense_search.assert_called_once()
    sparse_search.assert_called_once()


def test_common_uuid_fused(registry, searches):
    """Dense와 BM25의 동일 UUID를 중복 제거한다."""

    result = run_search(registry)

    matches = [item for item in result if item.kind == "chunk" and item.item_id == "B"]

    assert len(matches) == 1
    assert matches[0].methods == ("dense", "bm25")


def test_npc_knowledge_filter(registry, searches):
    """Qdrant 검색은 현재 NPC 지식으로 제한한다."""

    _, dense_search, sparse_search = searches

    run_search(registry)

    for search in (dense_search, sparse_search):
        kwargs = search.call_args.kwargs

        assert kwargs["source_type"] == "npc_knowledge"
        assert kwargs["character_id"] == "C01"
        assert kwargs["case_id"] == "CASE-001"


def test_locked_active_npc_blocked(registry, searches):
    """미해금 대화 NPC는 모든 DB 검색을 차단한다."""

    graph_search, dense_search, sparse_search = searches

    result = run_search(
        registry,
        state=make_state(unlocked=[]),
    )

    assert result == []

    graph_search.assert_not_called()
    dense_search.assert_not_called()
    sparse_search.assert_not_called()


def test_locked_target_blocks_all_search(registry, searches):
    """잠긴 인물을 질문하면 전체 검색을 차단한다."""

    graph_search, dense_search, sparse_search = searches

    result = run_search(
        registry,
        query="박민수와 무슨 관계인가요?",
        allowed_entity_ids=set(),
    )

    assert result == []

    graph_search.assert_not_called()
    dense_search.assert_not_called()
    sparse_search.assert_not_called()


def test_untrusted_qdrant_uuid_rejected(registry, searches):
    """서버 원본에 없는 Qdrant UUID를 거부한다."""

    with pytest.raises(
        ValueError,
        match="신뢰할 수 없는 Qdrant",
    ):
        run_search(
            registry,
            trusted_point_ids={"A", "C"},
        )


def test_results_have_no_content(registry, searches):
    """통합 후보에는 원본 문서 내용이 없다."""

    result = run_search(registry)

    for item in result:
        assert set(asdict(item)) == {
            "kind",
            "item_id",
            "score",
            "methods",
        }


def test_graph_only_search(registry, searches):
    """Qdrant 결과가 없어도 Graph 결과를 유지한다."""

    _, dense_search, sparse_search = searches

    dense_search.return_value = []
    sparse_search.return_value = []

    result = run_search(
        registry,
        trusted_point_ids=set(),
    )

    assert len(result) == 1
    assert result[0].kind == "relation"
    assert result[0].item_id == "REL-001"


def test_invalid_candidate_k(registry, searches):
    """잘못된 후보 개수를 거부한다."""

    with pytest.raises(ValueError, match="candidate_k"):
        run_search(registry, candidate_k=0)


def test_invalid_rrf_k(registry, searches):
    """잘못된 RRF 상수를 거부한다."""

    with pytest.raises(ValueError, match="rrf_k"):
        run_search(registry, rrf_k=0)


def test_invalid_character(registry, searches):
    """유효하지 않은 NPC ID를 차단한다."""

    with pytest.raises(ValueError, match="NPC ID"):
        run_search(
            registry,
            active_character_id="C99",
        )


def test_empty_question_rejected(registry, searches):
    """빈 질문을 검색하지 않는다."""

    with pytest.raises(ValueError, match="비어 있습니다"):
        run_search(
            registry,
            query="  ",
        )
