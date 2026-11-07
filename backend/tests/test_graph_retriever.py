"""통합 Graph Retriever 테스트."""

from unittest.mock import MagicMock

import pytest

import crimescene.retriever.graph_retriever as graph_module
from crimescene.retriever.graph_evidence_search import EvidenceGraphResult
from crimescene.retriever.graph_retriever import retrieve_character_graph
from crimescene.retriever.graph_search import GraphSearchResult
from crimescene.scenario.schemas.game_state import GameState


def make_state(
    *,
    unlocked=None,
    case_id="CASE-001",
):
    return GameState(
        case_id=case_id,
        session_id="GRAPH-TEST",
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


@pytest.fixture
def mock_searches(monkeypatch):
    relation_search = MagicMock(return_value=[])
    evidence_search = MagicMock(return_value=[])

    monkeypatch.setattr(
        graph_module,
        "search_character_relations",
        relation_search,
    )

    monkeypatch.setattr(
        graph_module,
        "search_character_evidence",
        evidence_search,
    )

    return relation_search, evidence_search


def test_combined_graph_search(mock_searches):
    """인물 관계와 증거를 하나의 결과로 반환한다."""

    relation_search, evidence_search = mock_searches

    relation = GraphSearchResult(
        edge_id="REL-001",
        source_id="C01",
        target_id="C05",
        neighbor_id="C05",
        relation="ROOMMATE_OF",
        truth_status="documented",
        access_scope="public",
        incident_year=2026,
    )

    evidence = EvidenceGraphResult(
        evidence_id="E01",
        holder_id="C01",
    )

    relation_search.return_value = [relation]
    evidence_search.return_value = [evidence]

    driver = MagicMock()
    state = make_state()
    edges = []
    rules = {}

    result = retrieve_character_graph(
        driver,
        "C01",
        state,
        edges,
        rules,
    )

    assert result.character_id == "C01"
    assert result.relations == (relation,)
    assert result.evidence == (evidence,)

    relation_search.assert_called_once_with(
        driver,
        "C01",
        state,
        edges,
        top_k=20,
    )

    evidence_search.assert_called_once_with(
        driver,
        "C01",
        state,
        rules,
        top_k=10,
    )


def test_locked_character_returns_empty(mock_searches):
    """미해금 NPC는 어떤 그래프도 검색하지 않는다."""

    relation_search, evidence_search = mock_searches

    result = retrieve_character_graph(
        MagicMock(),
        "C01",
        make_state(unlocked=[]),
        [],
        {},
    )

    assert result.relations == ()
    assert result.evidence == ()

    relation_search.assert_not_called()
    evidence_search.assert_not_called()


def test_wrong_case_rejected(mock_searches):
    """다른 사건의 GameState는 거부한다."""

    with pytest.raises(ValueError, match="지원하지 않는"):
        retrieve_character_graph(
            MagicMock(),
            "C01",
            make_state(case_id="CASE-999"),
            [],
            {},
        )


def test_invalid_character_rejected(mock_searches):
    """유효하지 않은 NPC ID를 거부한다."""

    with pytest.raises(ValueError, match="유효하지 않은"):
        retrieve_character_graph(
            MagicMock(),
            "C99",
            make_state(),
            [],
            {},
        )


def test_invalid_state_rejected(mock_searches):
    """GameState가 아닌 입력을 거부한다."""

    with pytest.raises(TypeError, match="GameState"):
        retrieve_character_graph(
            MagicMock(),
            "C01",
            object(),
            [],
            {},
        )


@pytest.mark.parametrize(
    ("relation_top_k", "evidence_top_k"),
    [
        (0, 10),
        (20, 0),
        (True, 10),
        (20, 101),
    ],
)
def test_invalid_limits_rejected(
    mock_searches,
    relation_top_k,
    evidence_top_k,
):
    """검색 제한값이 잘못되면 요청을 거부한다."""

    with pytest.raises((TypeError, ValueError)):
        retrieve_character_graph(
            MagicMock(),
            "C01",
            make_state(),
            [],
            {},
            relation_top_k=relation_top_k,
            evidence_top_k=evidence_top_k,
        )
