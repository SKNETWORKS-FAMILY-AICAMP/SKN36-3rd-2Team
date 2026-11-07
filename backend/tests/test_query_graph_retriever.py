"""자연어 질문 기반 Graph Retrieval 테스트."""

from unittest.mock import MagicMock

import pytest

import crimescene.retriever.query_graph_retriever as module
from crimescene.retriever.graph_evidence_search import (
    EvidenceGraphResult,
)
from crimescene.retriever.graph_retriever import (
    CharacterGraphContext,
)
from crimescene.retriever.graph_search import (
    GraphSearchResult,
)
from crimescene.retriever.query_graph_retriever import (
    retrieve_question_graph,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GameState,
)

# ==================================================
# Fixtures
# ==================================================


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
            "entity_id": "P01",
            "type": "Place",
            "label": "세린국제학교",
        },
    ]


def make_state(
    *,
    unlocked=None,
    evidence=None,
):
    return GameState(
        case_id="CASE-001",
        session_id="QUESTION-GRAPH-TEST",
        unlocked_characters=(["C01", "C02"] if unlocked is None else unlocked),
        evidence=({} if evidence is None else evidence),
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
    return CharacterGraphContext(
        character_id="C01",
        relations=(
            GraphSearchResult(
                edge_id="REL-001",
                source_id="C01",
                target_id="P01",
                neighbor_id="P01",
                relation="VISITED",
                truth_status="documented",
                access_scope="public",
                incident_year=2026,
            ),
            GraphSearchResult(
                edge_id="REL-002",
                source_id="C01",
                target_id="C02",
                neighbor_id="C02",
                relation="KNOWS",
                truth_status="documented",
                access_scope="public",
                incident_year=2026,
            ),
        ),
        evidence=(
            EvidenceGraphResult(
                evidence_id="E01",
                holder_id="C01",
            ),
        ),
    )


@pytest.fixture
def mock_graph(monkeypatch):
    search = MagicMock(return_value=make_graph())

    monkeypatch.setattr(
        module,
        "retrieve_character_graph",
        search,
    )

    return search


def run_query(
    query,
    registry,
    **kwargs,
):
    return retrieve_question_graph(
        query,
        driver=MagicMock(),
        active_character_id="C01",
        state=kwargs.pop(
            "state",
            make_state(),
        ),
        registry=registry,
        trusted_edges=[],
        evidence_rules=kwargs.pop(
            "evidence_rules",
            {},
        ),
        **kwargs,
    )


# ==================================================
# 기존 기능 테스트
# ==================================================


def test_question_filters_place_relations(
    registry,
    mock_graph,
):
    """질문의 장소와 연결된 관계만 반환한다."""

    result = run_query(
        "세린국제학교에서 누구를 만났어?",
        registry,
        allowed_entity_ids={"P01"},
    )

    assert [item.edge_id for item in result.relations] == ["REL-001"]

    assert result.evidence == ()

    assert result.matched_entity_ids == ("P01",)

    mock_graph.assert_called_once()


def test_question_filters_person_relations(
    registry,
    mock_graph,
):
    """질문에 언급된 인물 관계만 반환한다."""

    result = run_query(
        "박민수와 어떤 관계야?",
        registry,
    )

    assert [item.edge_id for item in result.relations] == ["REL-002"]


def test_active_character_question(
    registry,
    mock_graph,
):
    """현재 대화 NPC에 관한 일반 질문."""

    result = run_query(
        "김서연은 누구를 알고 있어?",
        registry,
    )

    assert len(result.relations) == 2
    assert len(result.evidence) == 1


def test_collected_evidence_filter(
    registry,
    mock_graph,
):
    """수집한 증거 관련 결과만 반환한다."""

    rule = EvidenceRule(
        name="목격자 진술서",
        score=10,
        holder="C01",
        prerequisites=[],
        presentation=[],
        q=[],
    )

    state = make_state(evidence={"E01": EvidenceState(stage="found")})

    result = run_query(
        "목격자 진술서에 대해 알려줘",
        registry,
        state=state,
        evidence_rules={"E01": rule},
    )

    assert result.relations == ()

    assert [item.evidence_id for item in result.evidence] == ["E01"]


def test_locked_character_does_not_query_db(
    registry,
    mock_graph,
):
    """현재 대화 NPC가 잠겨 있으면 검색하지 않는다."""

    result = run_query(
        "김서연에 대해 알려줘",
        registry,
        state=make_state(unlocked=[]),
    )

    assert result.relations == ()
    assert result.evidence == ()

    mock_graph.assert_not_called()


def test_empty_query_rejected(
    registry,
    mock_graph,
):
    """빈 질문 차단."""

    with pytest.raises(
        ValueError,
        match="유효한 질문",
    ):
        run_query(
            " ",
            registry,
        )

    mock_graph.assert_not_called()


def test_invalid_character_rejected(
    registry,
    mock_graph,
):
    """잘못된 NPC ID 차단."""

    with pytest.raises(
        ValueError,
        match="유효하지 않은",
    ):
        retrieve_question_graph(
            "누구야?",
            driver=MagicMock(),
            active_character_id="C99",
            state=make_state(),
            registry=registry,
            trusted_edges=[],
            evidence_rules={},
        )

    mock_graph.assert_not_called()


def test_invalid_limit_rejected(
    registry,
    mock_graph,
):
    """잘못된 검색 제한값 차단."""

    with pytest.raises(
        ValueError,
        match="relation_top_k",
    ):
        run_query(
            "김서연은 누구야?",
            registry,
            relation_top_k=0,
        )

    mock_graph.assert_not_called()


# ==================================================
# 신규 보안 테스트
# ==================================================


def test_locked_target_does_not_fallback(
    registry,
    mock_graph,
):
    """미해금 NPC 질문을 일반 관계 검색으로 대체하지 않는다."""

    result = run_query(
        "박민수와 무슨 관계야?",
        registry,
        state=make_state(unlocked=["C01"]),
    )

    assert result.matched_entity_ids == ()
    assert result.relations == ()
    assert result.evidence == ()

    mock_graph.assert_not_called()


def test_mixed_visible_and_locked_entities_blocked(
    registry,
    mock_graph,
):
    """공개 장소와 잠긴 NPC를 함께 언급해도 차단한다."""

    result = run_query(
        "세린국제학교에서 박민수를 만났어?",
        registry,
        state=make_state(unlocked=["C01"]),
        allowed_entity_ids={"P01"},
    )

    assert result.matched_entity_ids == ()
    assert result.relations == ()
    assert result.evidence == ()

    mock_graph.assert_not_called()


def test_uncollected_evidence_does_not_fallback(
    registry,
    mock_graph,
):
    """미수집 증거 질문을 일반 관계 검색으로 대체하지 않는다."""

    rule = EvidenceRule(
        name="목격자 진술서",
        score=10,
        holder="C01",
        prerequisites=[],
        presentation=[],
        q=[],
    )

    result = run_query(
        "목격자 진술서에 대해 알려줘",
        registry,
        evidence_rules={"E01": rule},
    )

    assert result.matched_entity_ids == ()
    assert result.relations == ()
    assert result.evidence == ()

    mock_graph.assert_not_called()


def test_general_question_still_retrieves_graph(
    registry,
    mock_graph,
):
    """엔티티가 없는 일반 질문은 기존 검색을 유지한다."""

    result = run_query(
        "당신은 누구를 알고 있나요?",
        registry,
    )

    assert len(result.relations) == 2
    assert len(result.evidence) == 1

    mock_graph.assert_called_once()
