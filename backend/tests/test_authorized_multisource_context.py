"""3중 Hybrid RAG 최종 접근 제어 테스트."""

from dataclasses import asdict
from uuid import NAMESPACE_URL, uuid5

import pytest

from crimescene.ingest.chunking_config import ChunkingConfig, ChunkingMode
from crimescene.ingest.hybrid_chunker import build_hybrid_chunks
from crimescene.ingest.npc_knowledge_chunker import build_npc_knowledge_chunks
from crimescene.retriever.authorized_multisource_context import (
    build_authorized_multisource_context,
)
from crimescene.retriever.graph_search import GraphSearchResult
from crimescene.retriever.multisource_rrf import FusedSearchCandidate
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge


def make_policy(*, character="C01", evidence=()):
    return AccessPolicy(
        required_evidence=list(evidence),
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character=character,
    )


def make_card(card_id, character, policy_id):
    body = f"{card_id} 테스트 진술"

    return {
        "id": card_id,
        "case_id": "CASE-001",
        "character_id": character,
        "policy_id": policy_id,
        "body": body,
        "search_text": body,
        "family": "npc_knowledge",
        "access_scope": "character_only",
        "truth_status": "character_claim",
        "required_evidence": [],
        "required_presentations": [],
        "required_flags": [],
        "required_ending": None,
        "required_topics": [],
        "required_disclosed_cards": [],
        "required_character": character,
        "supersedes": [],
        "stage_priority": 0,
        "point_id": str(uuid5(NAMESPACE_URL, card_id)),
        "incident_year": 2026,
        "content_hash": f"hash-{card_id}",
    }


def make_state(*, unlocked=None):
    return GameState(
        case_id="CASE-001",
        session_id="MULTISOURCE-AUTH-TEST",
        unlocked_characters=["C01"] if unlocked is None else unlocked,
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


def make_edge():
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
            "truth_status": "witness_statement",
            "source_doc_ids": ["DOC-SECRET"],
            "asserted_by": [],
            "access_scope": "public",
            "required_evidence": [],
            "required_presentations": [],
            "required_flags": [],
            "required_ending": None,
        }
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
                truth_status="witness_statement",
                access_scope="public",
                incident_year=2026,
            ),
        ),
        evidence=(),
    )


def candidate(kind, item_id, score):
    methods = ("dense", "bm25") if kind == "chunk" else ("graph",)

    return FusedSearchCandidate(
        kind=kind,
        item_id=item_id,
        score=score,
        methods=methods,
    )


@pytest.fixture
def case_data():
    policies = {
        "POL-OPEN": make_policy(),
        "POL-LOCKED": make_policy(evidence=["E01"]),
        "POL-C02": make_policy(character="C02"),
    }

    cards = [
        make_card("K-C01-OPEN", "C01", "POL-OPEN"),
        make_card("K-C01-LOCKED", "C01", "POL-LOCKED"),
        make_card("K-C02-ONLY", "C02", "POL-C02"),
    ]

    chunks = build_npc_knowledge_chunks(
        cards,
        expected_case_id="CASE-001",
        valid_policy_ids=set(policies),
    )

    records = build_hybrid_chunks(
        chunks,
        ChunkingConfig(mode=ChunkingMode.WHOLE),
    )

    ids = {record.chunk.source_id: record.chunk.point_id for record in records}

    return {
        "records": records,
        "cards": cards,
        "ids": ids,
        "evaluator": PolicyEvaluator(policies),
        "edges": [make_edge()],
        "registry": [
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
        ],
    }


def run_context(data, candidates, **kwargs):
    return build_authorized_multisource_context(
        candidates,
        trusted_records=data["records"],
        documents=[],
        npc_cards=data["cards"],
        graph_context=kwargs.pop("graph_context", make_graph()),
        registry=data["registry"],
        trusted_edges=data["edges"],
        evidence_rules={},
        state=kwargs.pop("state", make_state()),
        evaluator=data["evaluator"],
        active_character_id="C01",
        allowed_entity_ids=kwargs.pop(
            "allowed_entity_ids",
            {"SERIN_SCHOOL"},
        ),
        **kwargs,
    )


def test_chunk_and_graph_context(case_data):
    """NPC 지식과 Graph 근거를 함께 반환한다."""

    result = run_context(
        case_data,
        [
            candidate(
                "chunk",
                case_data["ids"]["K-C01-OPEN"],
                0.04,
            ),
            candidate("relation", "REL-001", 0.02),
        ],
    )

    assert len(result.items) == 2
    assert result.items[0].kind == "chunk"
    assert result.items[1].kind == "relation"
    assert "K-C01-OPEN 테스트 진술" in result.text
    assert "REL-001" in result.text


def test_locked_card_removed(case_data):
    """수집 조건을 충족하지 않은 NPC 카드를 제거한다."""

    result = run_context(
        case_data,
        [
            candidate(
                "chunk",
                case_data["ids"]["K-C01-LOCKED"],
                0.04,
            ),
        ],
    )

    assert result.items == ()
    assert "K-C01-LOCKED" not in result.text


def test_top_k_after_authorization(case_data):
    """비공개 상위 후보를 제거한 뒤 Top-K를 적용한다."""

    result = run_context(
        case_data,
        [
            candidate(
                "chunk",
                case_data["ids"]["K-C01-LOCKED"],
                0.05,
            ),
            candidate(
                "chunk",
                case_data["ids"]["K-C01-OPEN"],
                0.04,
            ),
            candidate("relation", "REL-001", 0.03),
        ],
        top_k=1,
    )

    assert len(result.items) == 1
    assert result.items[0].source_id == "K-C01-OPEN"


def test_other_npc_knowledge_blocked(case_data):
    """다른 NPC의 지식은 현재 NPC에게 전달하지 않는다."""

    result = run_context(
        case_data,
        [
            candidate(
                "chunk",
                case_data["ids"]["K-C02-ONLY"],
                0.04,
            )
        ],
    )

    assert result.items == ()


def test_unapproved_graph_relation_hidden(case_data):
    """허용되지 않은 장소 관계는 최종 컨텍스트에서 제거한다."""

    result = run_context(
        case_data,
        [candidate("relation", "REL-001", 0.02)],
        allowed_entity_ids=set(),
    )

    assert result.items == ()
    assert "세린국제학교" not in result.text


def test_graph_document_reference_hidden(case_data):
    """Graph가 참조하는 비공개 문서 ID는 전달하지 않는다."""

    result = run_context(
        case_data,
        [candidate("relation", "REL-001", 0.02)],
    )

    assert len(result.items) == 1
    assert "DOC-SECRET" not in result.text
    assert "사실 확정 아님" in result.text


def test_unknown_qdrant_uuid_rejected(case_data):
    """신뢰 원본에 없는 UUID는 거부한다."""

    with pytest.raises(ValueError, match="신뢰할 수 없는"):
        run_context(
            case_data,
            [candidate("chunk", "UNKNOWN", 0.03)],
        )


def test_unknown_graph_relation_rejected(case_data):
    """실제 검색 결과에 없는 관계 ID는 거부한다."""

    with pytest.raises(ValueError, match="신뢰할 수 없는"):
        run_context(
            case_data,
            [candidate("relation", "REL-999", 0.03)],
        )


def test_locked_active_npc_returns_empty(case_data):
    """현재 NPC가 잠기면 모든 근거를 차단한다."""

    result = run_context(
        case_data,
        [candidate("relation", "REL-001", 0.03)],
        state=make_state(unlocked=[]),
    )

    assert result.items == ()


def test_duplicate_fused_candidate_rejected(case_data):
    """동일한 통합 검색 후보의 중복을 차단한다."""

    item = candidate("relation", "REL-001", 0.02)

    with pytest.raises(ValueError, match="중복"):
        run_context(case_data, [item, item])


def test_output_contains_only_approved_fields(case_data):
    """LLM 근거 모델에 내부 접근 정책 정보가 없는지 확인한다."""

    result = run_context(
        case_data,
        [candidate("relation", "REL-001", 0.02)],
    )

    fields = set(asdict(result.items[0]))

    assert fields == {
        "kind",
        "item_id",
        "source_id",
        "score",
        "methods",
        "content",
        "truth_status",
    }

    assert "policy_id" not in result.text
    assert "DOC-SECRET" not in result.text
