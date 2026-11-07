"""NPC별 Qdrant 검색 전 접근 제어 테스트."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import NAMESPACE_URL, uuid5

import pytest
from qdrant_client import models

import crimescene.retriever.npc_presearch_access as module
from crimescene.ingest.chunking_config import ChunkingConfig, ChunkingMode
from crimescene.ingest.hybrid_chunker import build_hybrid_chunks
from crimescene.ingest.npc_knowledge_chunker import build_npc_knowledge_chunks
from crimescene.retriever.multisource_rrf import FusedSearchCandidate
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import EvidenceState, GameState

CASE_ID = "CASE-001"


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
        "case_id": CASE_ID,
        "character_id": character,
        "policy_id": policy_id,
        "body": body,
        "search_text": body,
        "family": "npc_knowledge",
        "access_scope": "character_only",
        "truth_status": "character_claim",
        "required_evidence": (["E01"] if card_id == "K-C01-LOCKED" else []),
        "required_presentations": [],
        "required_flags": [],
        "required_ending": None,
        "required_topics": [],
        "required_disclosed_cards": [],
        "required_character": character,
        "supersedes": [],
        "stage_priority": 0,
        "point_id": str(uuid5(NAMESPACE_URL, card_id)),
        "incident_year": 2016,
        "content_hash": f"hash-{card_id}",
    }


def make_state(*, unlocked=None, collected=()):
    return GameState(
        case_id=CASE_ID,
        session_id="NPC-PRESEARCH-TEST",
        unlocked_characters=(["C01"] if unlocked is None else unlocked),
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
        expected_case_id=CASE_ID,
        valid_policy_ids=set(policies),
    )

    records = build_hybrid_chunks(
        chunks,
        ChunkingConfig(mode=ChunkingMode.WHOLE),
    )

    return {
        "records": records,
        "cards": cards,
        "evaluator": PolicyEvaluator(policies),
        "ids": {card["id"]: card["point_id"] for card in cards},
    }


def allowed_ids(data, state):
    return module.build_authorized_npc_point_ids(
        trusted_records=data["records"],
        npc_cards=data["cards"],
        state=state,
        evaluator=data["evaluator"],
        active_character_id="C01",
    )


def test_open_card_allowed(case_data):
    """현재 NPC의 공개 지식만 허용한다."""

    result = allowed_ids(case_data, make_state())

    assert result == {
        case_data["ids"]["K-C01-OPEN"],
    }


def test_locked_card_blocked(case_data):
    """미수집 증거가 필요한 지식은 검색 전에 차단한다."""

    result = allowed_ids(case_data, make_state())

    assert case_data["ids"]["K-C01-LOCKED"] not in result


def test_collected_evidence_unlocks_card(case_data):
    """증거 획득 후 접근 가능한 UUID가 늘어난다."""

    result = allowed_ids(
        case_data,
        make_state(collected=["E01"]),
    )

    assert result == {
        case_data["ids"]["K-C01-OPEN"],
        case_data["ids"]["K-C01-LOCKED"],
    }


def test_other_npc_knowledge_blocked(case_data):
    """다른 NPC의 지식은 검색 대상에 포함하지 않는다."""

    result = allowed_ids(case_data, make_state())

    assert case_data["ids"]["K-C02-ONLY"] not in result


def test_locked_npc_has_no_allowed_ids(case_data):
    """미해금 NPC의 검색 가능한 UUID는 없다."""

    result = allowed_ids(
        case_data,
        make_state(unlocked=[]),
    )

    assert result == frozenset()


def test_qdrant_has_id_filter_applied(case_data):
    """Qdrant 검색에 승인된 UUID 조건이 추가된다."""

    client = MagicMock()

    client.query_points.return_value = SimpleNamespace(points=[])

    approved_id = case_data["ids"]["K-C01-OPEN"]

    scoped = module.PolicyScopedQdrantClient(
        client,
        {approved_id},
    )

    original_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="case_id",
                match=models.MatchValue(value=CASE_ID),
            ),
            models.FieldCondition(
                key="source_type",
                match=models.MatchValue(value="npc_knowledge"),
            ),
            models.FieldCondition(
                key="character_id",
                match=models.MatchValue(value="C01"),
            ),
        ]
    )

    scoped.query_points(
        collection_name="test_collection",
        query=[0.1, 0.2],
        query_filter=original_filter,
        limit=10,
    )

    client.query_points.assert_called_once()

    secured_filter = client.query_points.call_args.kwargs["query_filter"]

    assert len(secured_filter.must) == 4

    assert secured_filter.must[:3] == original_filter.must

    id_conditions = [
        item for item in secured_filter.must if isinstance(item, models.HasIdCondition)
    ]

    assert len(id_conditions) == 1
    assert approved_id in id_conditions[0].has_id

    # 기존 Filter를 변경하지 않아야 한다.
    assert len(original_filter.must) == 3


def test_empty_allowed_ids_skip_qdrant():
    """허용된 UUID가 없으면 Qdrant 검색 요청을 하지 않는다."""

    client = MagicMock()

    scoped = module.PolicyScopedQdrantClient(
        client,
        [],
    )

    result = scoped.query_points(
        query_filter=models.Filter(must=[]),
    )

    assert result.points == []
    client.query_points.assert_not_called()


def test_invalid_uuid_rejected():
    """잘못된 UUID는 검색 조건에 포함하지 않는다."""

    with pytest.raises(ValueError, match="UUID"):
        module.PolicyScopedQdrantClient(
            MagicMock(),
            ["INVALID-UUID"],
        )


def test_missing_qdrant_filter_rejected():
    """필수 검색 필터가 없는 요청은 차단한다."""

    scoped = module.PolicyScopedQdrantClient(
        MagicMock(),
        [],
    )

    with pytest.raises(TypeError, match="검색 필터"):
        scoped.query_points()


def test_policy_scoped_search_uses_wrapper(
    case_data,
    monkeypatch,
):
    """통합 검색에 정책 제한 Qdrant 클라이언트를 사용한다."""

    mock_search = MagicMock(return_value=[])

    monkeypatch.setattr(
        module,
        "search_multisource_candidates",
        mock_search,
    )

    module.search_policy_scoped_multisource_candidates(
        "세린국제학교에 대해 알려줘",
        qdrant_client=MagicMock(),
        neo4j_driver=MagicMock(),
        embedder=MagicMock(),
        encoder=MagicMock(),
        state=make_state(),
        evaluator=case_data["evaluator"],
        active_character_id="C01",
        trusted_records=case_data["records"],
        npc_cards=case_data["cards"],
        registry=[],
        trusted_edges=[],
        evidence_rules={},
    )

    mock_search.assert_called_once()

    scoped = mock_search.call_args.kwargs["qdrant_client"]

    assert isinstance(
        scoped,
        module.PolicyScopedQdrantClient,
    )

    assert scoped.allowed_point_ids == (case_data["ids"]["K-C01-OPEN"],)


def test_unapproved_search_result_rejected(
    case_data,
    monkeypatch,
):
    """DB가 비공개 UUID를 반환해도 최종 후보에서 차단한다."""

    leaked = FusedSearchCandidate(
        kind="chunk",
        item_id=case_data["ids"]["K-C01-LOCKED"],
        score=0.03,
        methods=("dense",),
    )

    monkeypatch.setattr(
        module,
        "search_multisource_candidates",
        MagicMock(return_value=[leaked]),
    )

    with pytest.raises(ValueError, match="접근 권한이 없는"):
        module.search_policy_scoped_multisource_candidates(
            "사건에 대해 알려줘",
            qdrant_client=MagicMock(),
            neo4j_driver=MagicMock(),
            embedder=MagicMock(),
            encoder=MagicMock(),
            state=make_state(),
            evaluator=case_data["evaluator"],
            active_character_id="C01",
            trusted_records=case_data["records"],
            npc_cards=case_data["cards"],
            registry=[],
            trusted_edges=[],
            evidence_rules={},
        )
