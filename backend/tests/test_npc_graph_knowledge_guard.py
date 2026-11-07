"""NPC별 Graph 지식 범위 및 정보 유출 차단 테스트."""

from dataclasses import replace

import pytest

from crimescene.retriever.graph_evidence_search import EvidenceGraphResult
from crimescene.retriever.graph_search import GraphSearchResult
from crimescene.retriever.multisource_rrf import FusedSearchCandidate
from crimescene.retriever.npc_graph_knowledge_guard import (
    restrict_npc_graph_knowledge,
)
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge


def make_state(*, unlocked=None, collected=()):
    return GameState(
        case_id="CASE-001",
        session_id="NPC-GRAPH-GUARD-TEST",
        unlocked_characters=["C01"] if unlocked is None else unlocked,
        evidence={item: EvidenceState(stage="found") for item in collected},
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


def make_edge(*, scope="public", required_evidence=()):
    return RelationshipSourceEdge.model_validate(
        {
            "case_id": "CASE-001",
            "edge_id": "REL-001",
            "source_id": "C01",
            "target_id": "SERIN_SCHOOL",
            "relation": "VISITED",
            "incident_year": 2016,
            "valid_from": "2016-01-01",
            "valid_to": "2016-12-31",
            "temporal_precision": "day",
            "truth_status": "witness_statement",
            "source_doc_ids": [],
            "asserted_by": [],
            "access_scope": scope,
            "required_evidence": list(required_evidence),
            "required_presentations": [],
            "required_flags": [],
            "required_ending": None,
        }
    )


def make_relation(edge):
    return GraphSearchResult(
        edge_id=edge.edge_id,
        source_id=edge.source_id,
        target_id=edge.target_id,
        neighbor_id=edge.target_id,
        relation=edge.relation,
        truth_status=edge.truth_status,
        access_scope=edge.access_scope,
        incident_year=edge.incident_year,
    )


def make_graph(*, relations=(), evidence=()):
    return QuestionGraphContext(
        character_id="C01",
        matched_entity_ids=("SERIN_SCHOOL",),
        relations=tuple(relations),
        evidence=tuple(evidence),
    )


def make_candidate(kind, item_id):
    return FusedSearchCandidate(
        kind=kind,
        item_id=item_id,
        score=0.02,
        methods=(("dense", "bm25") if kind == "chunk" else ("graph",)),
    )


def run_guard(
    candidates,
    graph,
    *,
    edge=None,
    state=None,
    known_relations=(),
    known_evidence=(),
    evidence_rules=None,
):
    return restrict_npc_graph_knowledge(
        candidates,
        graph,
        state=make_state() if state is None else state,
        active_character_id="C01",
        trusted_edges=[make_edge() if edge is None else edge],
        evidence_rules={} if evidence_rules is None else evidence_rules,
        known_relation_ids=known_relations,
        known_evidence_ids=known_evidence,
    )


def test_default_denies_graph_relation():
    """명시적으로 승인하지 않은 Graph 관계는 차단한다."""

    edge = make_edge()
    graph = make_graph(relations=[make_relation(edge)])

    result = run_guard(
        [make_candidate("relation", "REL-001")],
        graph,
    )

    assert result.candidates == ()
    assert result.graph_context.relations == ()


def test_explicit_relation_grant_allows():
    """현재 NPC에게 승인된 관계만 허용한다."""

    edge = make_edge()
    graph = make_graph(relations=[make_relation(edge)])

    result = run_guard(
        [make_candidate("relation", "REL-001")],
        graph,
        known_relations={"REL-001"},
    )

    assert len(result.candidates) == 1
    assert result.graph_context.relations[0].edge_id == "REL-001"


def test_chunk_candidates_preserved():
    """기존 Qdrant 청크 후보는 다음 정책 검증 단계로 전달한다."""

    edge = make_edge()
    graph = make_graph(relations=[make_relation(edge)])

    result = run_guard(
        [
            make_candidate("chunk", "UUID-001"),
            make_candidate("relation", "REL-001"),
        ],
        graph,
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].kind == "chunk"
    assert result.graph_context.relations == ()


def test_locked_active_npc_denies_all():
    """대화 NPC가 잠겨 있으면 모든 후보를 차단한다."""

    edge = make_edge()
    graph = make_graph(relations=[make_relation(edge)])

    result = run_guard(
        [
            make_candidate("chunk", "UUID-001"),
            make_candidate("relation", "REL-001"),
        ],
        graph,
        state=make_state(unlocked=[]),
        known_relations={"REL-001"},
    )

    assert result.candidates == ()
    assert result.graph_context.relations == ()


def test_conditional_relation_requires_collected_evidence():
    """NPC가 아는 관계라도 공개 조건을 충족해야 한다."""

    edge = make_edge(
        scope="conditional",
        required_evidence=["E01"],
    )
    graph = make_graph(relations=[make_relation(edge)])

    candidates = [
        make_candidate("relation", "REL-001"),
    ]

    blocked = run_guard(
        candidates,
        graph,
        edge=edge,
        known_relations={"REL-001"},
    )

    allowed = run_guard(
        candidates,
        graph,
        edge=edge,
        state=make_state(collected=["E01"]),
        known_relations={"REL-001"},
    )

    assert blocked.candidates == ()
    assert len(allowed.candidates) == 1


def test_unknown_relation_grant_rejected():
    """원본에 없는 관계를 NPC 지식으로 승인할 수 없다."""

    edge = make_edge()
    graph = make_graph(relations=[make_relation(edge)])

    with pytest.raises(ValueError, match="존재하지 않는"):
        run_guard(
            [make_candidate("relation", "REL-001")],
            graph,
            known_relations={"REL-999"},
        )


def test_forged_relation_rejected():
    """Neo4j 관계 검색 결과가 원본과 다르면 차단한다."""

    edge = make_edge()

    forged = replace(
        make_relation(edge),
        relation="SECRET_RELATION",
    )

    graph = make_graph(relations=[forged])

    with pytest.raises(ValueError, match="원본이 일치하지"):
        run_guard(
            [make_candidate("relation", "REL-001")],
            graph,
            known_relations={"REL-001"},
        )


def test_uncollected_evidence_blocked():
    """NPC에게 승인된 증거라도 플레이어가 미수집하면 차단한다."""

    rule = EvidenceRule(
        name="테스트 진술서",
        score=10,
        holder="C01",
        prerequisites=[],
        presentation=[],
        q=[],
    )

    graph = make_graph(
        evidence=[
            EvidenceGraphResult(
                evidence_id="E01",
                holder_id="C01",
            )
        ]
    )

    candidates = [
        make_candidate("evidence", "E01"),
    ]

    blocked = run_guard(
        candidates,
        graph,
        known_evidence={"E01"},
        evidence_rules={"E01": rule},
    )

    allowed = run_guard(
        candidates,
        graph,
        state=make_state(collected=["E01"]),
        known_evidence={"E01"},
        evidence_rules={"E01": rule},
    )

    assert blocked.candidates == ()
    assert len(allowed.candidates) == 1


def test_unmatched_graph_candidate_rejected():
    """Graph 검색에 없던 관계를 RRF 후보에 추가하면 거부한다."""

    with pytest.raises(ValueError, match="Graph 검색 결과에 없는"):
        run_guard(
            [make_candidate("relation", "REL-001")],
            make_graph(),
            known_relations={"REL-001"},
        )
