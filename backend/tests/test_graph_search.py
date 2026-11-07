from unittest.mock import MagicMock

import pytest

from crimescene.retriever.graph_search import (
    is_relation_visible,
    search_character_relations,
)
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GameState,
)
from crimescene.scenario.schemas.relationship import (
    RelationshipSourceEdge,
)


def make_state(*, unlocked=None, evidence=None):
    return GameState(
        case_id="CASE-001",
        session_id="TEST",
        unlocked_characters=(["C01", "C02"] if unlocked is None else unlocked),
        evidence={} if evidence is None else evidence,
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


def make_edge(*, scope="public", required_evidence=None):
    return RelationshipSourceEdge.model_validate(
        {
            "case_id": "CASE-001",
            "edge_id": "REL-001",
            "source_id": "C01",
            "target_id": "C02",
            "relation": "KNOWS",
            "incident_year": 2026,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "temporal_precision": "day",
            "truth_status": "documented",
            "source_doc_ids": [],
            "asserted_by": [],
            "access_scope": scope,
            "required_evidence": required_evidence or [],
            "required_presentations": [],
            "required_flags": [],
            "required_ending": None,
        }
    )


def make_driver(edge_id="REL-001"):
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value

    session.run.return_value.data.return_value = [{"edge_id": edge_id}]

    return driver


def test_public_relation():
    """공개 관계 검색."""

    results = search_character_relations(
        make_driver(),
        "C01",
        make_state(),
        [make_edge()],
    )

    assert len(results) == 1
    assert results[0].neighbor_id == "C02"
    assert results[0].relation == "KNOWS"


def test_locked_character():
    """미해금 인물 접근 차단."""

    results = search_character_relations(
        make_driver(),
        "C01",
        make_state(unlocked=["C02"]),
        [make_edge()],
    )

    assert results == []


def test_locked_neighbor():
    """상대 인물이 잠겨 있으면 관계 비공개."""

    results = search_character_relations(
        make_driver(),
        "C01",
        make_state(unlocked=["C01"]),
        [make_edge()],
    )

    assert results == []


def test_conditional_relation():
    """증거 획득 전후 공개 상태 변화."""

    edge = make_edge(
        scope="conditional",
        required_evidence=["E05"],
    )

    assert not is_relation_visible(
        edge,
        make_state(),
    )

    assert is_relation_visible(
        edge,
        make_state(evidence={"E05": EvidenceState(stage="found")}),
    )


def test_unknown_graph_edge():
    """DB에만 존재하는 관계 ID 차단."""

    with pytest.raises(ValueError, match="신뢰할 수 없는"):
        search_character_relations(
            make_driver("REL-999"),
            "C01",
            make_state(),
            [make_edge()],
        )


def test_empty_conditional_policy():
    """공개 조건이 없는 조건부 관계 차단."""

    edge = make_edge(scope="conditional")

    assert not is_relation_visible(
        edge,
        make_state(),
    )


def test_uncollected_evidence_hidden():
    """수집하지 않은 증거와의 관계는 숨긴다."""

    edge = make_edge().model_copy(update={"target_id": "E05"})

    results = search_character_relations(
        make_driver(),
        "C01",
        make_state(),
        [edge],
    )

    assert results == []


def test_collected_evidence_visible():
    """증거 획득 후 관계를 조회할 수 있다."""

    edge = make_edge().model_copy(update={"target_id": "E05"})

    state = make_state(evidence={"E05": EvidenceState(stage="found")})

    results = search_character_relations(
        make_driver(),
        "C01",
        state,
        [edge],
    )

    assert len(results) == 1
    assert results[0].neighbor_id == "E05"
