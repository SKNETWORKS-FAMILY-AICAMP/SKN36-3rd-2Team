"""Graph RAG 컨텍스트 변환 및 정보 누출 방지 테스트."""

import pytest

from crimescene.retriever.graph_context_builder import (
    build_graph_rag_context,
)
from crimescene.retriever.graph_evidence_search import EvidenceGraphResult
from crimescene.retriever.graph_search import GraphSearchResult
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge


def make_state(*, unlocked=None, evidence=None):
    return GameState(
        case_id="CASE-001",
        session_id="GRAPH-CONTEXT-TEST",
        unlocked_characters=(["C01"] if unlocked is None else unlocked),
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


def make_edge(*, truth="documented", scope="public"):
    return RelationshipSourceEdge.model_validate(
        {
            "case_id": "CASE-001",
            "edge_id": "REL-001",
            "source_id": "C01",
            "target_id": "SERIN_SCHOOL",
            "relation": "VISITED",
            "incident_year": 2026,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "temporal_precision": "day",
            "truth_status": truth,
            "source_doc_ids": ["DOC-PUBLIC", "DOC-SECRET"],
            "asserted_by": [],
            "access_scope": scope,
            "required_evidence": [],
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
            "entity_id": "SERIN_SCHOOL",
            "type": "Institution",
            "label": "세린국제학교",
        },
    ]


def build(graph, registry, edges=None, **kwargs):
    return build_graph_rag_context(
        graph,
        state=kwargs.pop("state", make_state()),
        registry=registry,
        trusted_edges=edges or [],
        evidence_rules=kwargs.pop("evidence_rules", {}),
        **kwargs,
    )


def test_public_relation_to_context(registry):
    edge = make_edge()

    result = build(
        make_graph(relations=[make_relation(edge)]),
        registry,
        [edge],
        allowed_entity_ids={"SERIN_SCHOOL"},
    )

    assert result.relation_ids == ("REL-001",)
    assert "김서연" in result.text
    assert "세린국제학교" in result.text
    assert "VISITED" in result.text


def test_unapproved_document_ids_hidden(registry):
    edge = make_edge()

    result = build(
        make_graph(relations=[make_relation(edge)]),
        registry,
        [edge],
        allowed_entity_ids={"SERIN_SCHOOL"},
        allowed_document_ids={"DOC-PUBLIC"},
    )

    assert "DOC-PUBLIC" in result.text
    assert "DOC-SECRET" not in result.text


def test_locked_character_returns_no_context(registry):
    edge = make_edge()

    result = build(
        make_graph(relations=[make_relation(edge)]),
        registry,
        [edge],
        state=make_state(unlocked=[]),
        allowed_entity_ids={"SERIN_SCHOOL"},
    )

    assert result.relation_ids == ()
    assert "REL-001" not in result.text


def test_unapproved_place_hidden(registry):
    edge = make_edge()

    result = build(
        make_graph(relations=[make_relation(edge)]),
        registry,
        [edge],
    )

    assert result.relation_ids == ()
    assert "세린국제학교" not in result.text


def test_unknown_relation_rejected(registry):
    edge = make_edge()

    result = make_relation(edge)

    forged = GraphSearchResult(
        edge_id="REL-999",
        source_id=result.source_id,
        target_id=result.target_id,
        neighbor_id=result.neighbor_id,
        relation=result.relation,
        truth_status=result.truth_status,
        access_scope=result.access_scope,
        incident_year=result.incident_year,
    )

    with pytest.raises(ValueError, match="신뢰할 수 없는"):
        build(
            make_graph(relations=[forged]),
            registry,
            [edge],
            allowed_entity_ids={"SERIN_SCHOOL"},
        )


def test_modified_relation_rejected(registry):
    edge = make_edge()

    forged = GraphSearchResult(
        edge_id="REL-001",
        source_id="C01",
        target_id="SERIN_SCHOOL",
        neighbor_id="SERIN_SCHOOL",
        relation="SECRET_RELATION",
        truth_status="documented",
        access_scope="public",
        incident_year=2026,
    )

    with pytest.raises(ValueError, match="일치하지 않습니다"):
        build(
            make_graph(relations=[forged]),
            registry,
            [edge],
            allowed_entity_ids={"SERIN_SCHOOL"},
        )


def test_witness_statement_not_presented_as_fact(registry):
    edge = make_edge(truth="witness_statement")

    result = build(
        make_graph(relations=[make_relation(edge)]),
        registry,
        [edge],
        allowed_entity_ids={"SERIN_SCHOOL"},
    )

    assert "사실 확정 아님" in result.text


def test_evidence_only_after_collection(registry):
    rule = EvidenceRule(
        name="목격자 진술서",
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

    blocked = build(
        graph,
        registry,
        evidence_rules={"E01": rule},
    )

    allowed = build(
        graph,
        registry,
        state=make_state(evidence={"E01": EvidenceState(stage="found")}),
        evidence_rules={"E01": rule},
    )

    assert blocked.evidence_ids == ()
    assert allowed.evidence_ids == ("E01",)
    assert "목격자 진술서" in allowed.text


def test_conditional_relation_requires_evidence(registry):
    edge = make_edge(scope="conditional").model_copy(
        update={"required_evidence": ["E01"]}
    )

    graph = make_graph(relations=[make_relation(edge)])

    blocked = build(
        graph,
        registry,
        [edge],
        allowed_entity_ids={"SERIN_SCHOOL"},
    )

    allowed = build(
        graph,
        registry,
        [edge],
        state=make_state(evidence={"E01": EvidenceState(stage="found")}),
        allowed_entity_ids={"SERIN_SCHOOL"},
    )

    assert blocked.relation_ids == ()
    assert allowed.relation_ids == ("REL-001",)


def test_no_relations_returns_empty_context(registry):
    result = build(make_graph(), registry)

    assert result.relation_ids == ()
    assert result.evidence_ids == ()
    assert "공개 가능한 그래프 근거가 없습니다" in result.text
