"""GameState 기반 Hybrid Search 접근 제어 통합 테스트."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import NAMESPACE_URL, uuid5

import pytest

from crimescene.ingest.chunking_config import (
    ChunkingConfig,
    ChunkingMode,
)
from crimescene.ingest.hybrid_chunker import build_hybrid_chunks
from crimescene.ingest.npc_knowledge_chunker import (
    build_npc_knowledge_chunks,
)
from crimescene.ingest.player_document_chunker import (
    build_player_document_chunks,
)
from crimescene.retriever import authorized_hybrid_search
from crimescene.retriever.rrf_fusion import HybridSearchCandidate
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import EvidenceState, GameState

CASE_ID = "CASE-001"


def make_policy(*, evidence=(), character=None):
    """테스트용 접근 정책."""

    return AccessPolicy(
        required_evidence=list(evidence),
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character=character,
    )


def make_document(doc_id, policy_id, *, evidence=()):
    """테스트용 플레이어 문서."""

    body = f"{doc_id} 테스트 증거 내용"

    return PlayerDocument(
        doc_id=doc_id,
        case_id=CASE_ID,
        title=f"{doc_id} 테스트 문서",
        body=body,
        family="evidence",
        access_scope="collected_evidence",
        truth_status="documented_in_game",
        source_evidence_ids=list(evidence),
        known_by_character_ids=[],
        source_doc_ids=[],
        required_evidence=list(evidence),
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        protected_fact_ids=[],
        incident_year=2016,
        incident_years=[2016],
        source_refs=[],
        record_id=f"REC-{doc_id}",
        point_id=str(uuid5(NAMESPACE_URL, doc_id)),
        policy_id=policy_id,
        state_version="7.1",
        content_version="1.0",
        build_id="authorized-search-test",
        content_hash=f"hash-{doc_id}",
        search_text=body,
    )


def make_card(
    card_id,
    character_id,
    policy_id,
    *,
    evidence=(),
    supersedes=(),
):
    """테스트용 NPC 지식 카드."""

    body = f"{card_id} 테스트 진술"

    return {
        "id": card_id,
        "case_id": CASE_ID,
        "character_id": character_id,
        "policy_id": policy_id,
        "body": body,
        "search_text": body,
        "family": "npc_knowledge",
        "access_scope": "character_only",
        "truth_status": "character_claim",
        "required_evidence": list(evidence),
        "required_presentations": [],
        "required_flags": [],
        "required_ending": None,
        "required_topics": [],
        "required_disclosed_cards": [],
        "required_character": character_id,
        "supersedes": list(supersedes),
        "stage_priority": 1 if supersedes else 0,
        "point_id": str(uuid5(NAMESPACE_URL, card_id)),
        "incident_year": 2016,
        "content_hash": f"hash-{card_id}",
    }


def make_state(*, evidence=(), unlocked=()):
    """플레이어의 테스트용 진행 상태."""

    return GameState(
        case_id=CASE_ID,
        session_id="TEST-SESSION",
        unlocked_characters=list(unlocked),
        evidence={
            evidence_id: EvidenceState(stage="found") for evidence_id in evidence
        },
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
    """문서 2개와 NPC 카드 3개로 테스트 시나리오 구성."""

    policies = {
        "POL-DOC-OPEN": make_policy(),
        "POL-DOC-LOCKED": make_policy(evidence=["E01"]),
        "POL-C01-OLD": make_policy(character="C01"),
        "POL-C01-NEW": make_policy(
            evidence=["E02"],
            character="C01",
        ),
        "POL-C02": make_policy(character="C02"),
    }

    documents = [
        make_document(
            "DOC-OPEN",
            "POL-DOC-OPEN",
        ),
        make_document(
            "DOC-LOCKED",
            "POL-DOC-LOCKED",
            evidence=["E01"],
        ),
    ]

    cards = [
        make_card(
            "K-C01-OLD",
            "C01",
            "POL-C01-OLD",
        ),
        make_card(
            "K-C01-NEW",
            "C01",
            "POL-C01-NEW",
            evidence=["E02"],
            supersedes=["K-C01-OLD"],
        ),
        make_card(
            "K-C02-ONLY",
            "C02",
            "POL-C02",
        ),
    ]

    policy_ids = set(policies)

    document_chunks = build_player_document_chunks(
        documents,
        expected_case_id=CASE_ID,
        valid_policy_ids=policy_ids,
    )

    npc_chunks = build_npc_knowledge_chunks(
        cards,
        expected_case_id=CASE_ID,
        valid_policy_ids=policy_ids,
    )

    records = build_hybrid_chunks(
        document_chunks + npc_chunks,
        ChunkingConfig(mode=ChunkingMode.WHOLE),
    )

    by_source = {record.chunk.source_id: record.chunk.point_id for record in records}

    return {
        "documents": documents,
        "cards": cards,
        "records": records,
        "evaluator": PolicyEvaluator(policies),
        "by_source": by_source,
    }


def mock_candidates(monkeypatch, case_data, *source_ids):
    """Hybrid Search 결과를 가짜 UUID 후보로 대체한다."""

    candidates = [
        HybridSearchCandidate(
            point_id=case_data["by_source"][source_id],
            score=1.0 / (60 + rank),
        )
        for rank, source_id in enumerate(source_ids, start=1)
    ]

    search_mock = Mock(return_value=candidates)

    monkeypatch.setattr(
        authorized_hybrid_search,
        "search_hybrid_candidates",
        search_mock,
    )

    return search_mock


def run_authorized_search(case_data, state, **kwargs):
    """기존 접근 제어 통합 함수를 실행한다."""

    return authorized_hybrid_search.search_authorized_hybrid_context(
        "사건에 대해 알려주세요",
        client=None,
        embedder=None,
        encoder=None,
        trusted_records=case_data["records"],
        documents=case_data["documents"],
        npc_cards=case_data["cards"],
        state=state,
        evaluator=case_data["evaluator"],
        **kwargs,
    )


def source_ids(results):
    """승인된 문서 ID 목록."""

    return [item.source_id for item in results]


def test_uncollected_evidence_blocked(case_data, monkeypatch):
    """미수집 증거는 검색돼도 공개되지 않는다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "DOC-LOCKED",
        "DOC-OPEN",
    )

    results = run_authorized_search(
        case_data,
        make_state(),
    )

    assert source_ids(results) == ["DOC-OPEN"]


def test_collected_evidence_allowed(case_data, monkeypatch):
    """E01 수집 후 잠긴 문서가 공개된다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "DOC-LOCKED",
        "DOC-OPEN",
    )

    results = run_authorized_search(
        case_data,
        make_state(evidence=["E01"]),
    )

    assert source_ids(results) == [
        "DOC-LOCKED",
        "DOC-OPEN",
    ]


def test_top_k_applied_after_authorization(case_data, monkeypatch):
    """접근 권한 검증이 끝난 후 Top-K를 적용한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "DOC-LOCKED",
        "DOC-OPEN",
    )

    results = run_authorized_search(
        case_data,
        make_state(),
        candidate_k=10,
        top_k=1,
    )

    assert source_ids(results) == ["DOC-OPEN"]


def test_locked_npc_blocked(case_data, monkeypatch):
    """미해금 NPC의 지식은 공개하지 않는다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "K-C01-OLD",
    )

    results = run_authorized_search(
        case_data,
        make_state(),
        active_character_id="C01",
    )

    assert results == []


def test_unlocked_npc_initial_statement(case_data, monkeypatch):
    """C01 해금 후 초기 진술을 사용할 수 있다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "K-C01-OLD",
    )

    results = run_authorized_search(
        case_data,
        make_state(unlocked=["C01"]),
        active_character_id="C01",
    )

    assert source_ids(results) == ["K-C01-OLD"]


def test_new_statement_requires_evidence(case_data, monkeypatch):
    """E02를 수집하기 전에는 새로운 진술을 차단한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "K-C01-NEW",
        "K-C01-OLD",
    )

    results = run_authorized_search(
        case_data,
        make_state(unlocked=["C01"]),
        active_character_id="C01",
    )

    assert source_ids(results) == ["K-C01-OLD"]


def test_new_statement_supersedes_old(case_data, monkeypatch):
    """E02 수집 후 새 진술이 이전 진술을 대체한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "K-C01-OLD",
        "K-C01-NEW",
    )

    results = run_authorized_search(
        case_data,
        make_state(
            evidence=["E02"],
            unlocked=["C01"],
        ),
        active_character_id="C01",
    )

    assert source_ids(results) == ["K-C01-NEW"]


def test_supersedes_uses_all_npc_cards(case_data, monkeypatch):
    """새 진술이 검색 후보에 없어도 이전 진술을 차단한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "K-C01-OLD",
    )

    results = run_authorized_search(
        case_data,
        make_state(
            evidence=["E02"],
            unlocked=["C01"],
        ),
        active_character_id="C01",
    )

    assert results == []


def test_cross_npc_knowledge_blocked(case_data, monkeypatch):
    """C01 대화 중 C02 지식 공개를 차단한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "K-C02-ONLY",
    )

    results = run_authorized_search(
        case_data,
        make_state(unlocked=["C01", "C02"]),
        active_character_id="C01",
    )

    assert results == []


def test_npc_knowledge_blocked_in_player_mode(case_data, monkeypatch):
    """플레이어 조사 모드에서는 NPC 전용 지식을 제외한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "K-C01-OLD",
    )

    results = run_authorized_search(
        case_data,
        make_state(unlocked=["C01"]),
    )

    assert results == []


def test_player_document_blocked_in_npc_mode(case_data, monkeypatch):
    """NPC 대화 모드에서 플레이어 문서를 자동 공개하지 않는다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    results = run_authorized_search(
        case_data,
        make_state(unlocked=["C01"]),
        active_character_id="C01",
    )

    assert results == []


def test_unknown_qdrant_uuid_rejected(case_data, monkeypatch):
    """신뢰 원본에 없는 UUID는 오류 처리한다."""

    unknown = HybridSearchCandidate(
        point_id="00000000-0000-4000-8000-000000000000",
        score=0.01,
    )

    monkeypatch.setattr(
        authorized_hybrid_search,
        "search_hybrid_candidates",
        Mock(return_value=[unknown]),
    )

    with pytest.raises(
        ValueError,
        match="신뢰할 수 없는 검색 후보 UUID",
    ):
        run_authorized_search(
            case_data,
            make_state(),
        )


def test_empty_search_results(case_data, monkeypatch):
    """검색 후보가 없으면 빈 목록을 반환한다."""

    monkeypatch.setattr(
        authorized_hybrid_search,
        "search_hybrid_candidates",
        Mock(return_value=[]),
    )

    results = run_authorized_search(
        case_data,
        make_state(),
    )

    assert results == []


def test_authorized_output_contains_safe_fields(case_data, monkeypatch):
    """승인된 결과는 LLM용 필드만 포함한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    results = run_authorized_search(
        case_data,
        make_state(),
    )

    assert len(results) == 1

    data = results[0].model_dump()

    assert set(data) == {
        "source_id",
        "source_type",
        "content",
        "truth_status",
        "character_id",
    }

    assert "policy_id" not in data
    assert "protected_fact_ids" not in data
    assert "supersedes" not in data


def test_search_filters_and_candidate_count(case_data, monkeypatch):
    """Hybrid Search에 올바른 검색 조건을 전달한다."""

    search_mock = mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    run_authorized_search(
        case_data,
        make_state(),
        candidate_k=20,
        top_k=5,
    )

    kwargs = search_mock.call_args.kwargs

    assert kwargs["source_type"] == "player_document"
    assert kwargs["case_id"] == CASE_ID
    assert kwargs["character_id"] is None
    assert kwargs["candidate_k"] == 20
    assert kwargs["top_k"] == 20


def test_duplicate_trusted_uuid_rejected(case_data, monkeypatch):
    """신뢰 청크 목록의 UUID 중복을 차단한다."""

    search_mock = mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    duplicate_records = [
        *case_data["records"],
        case_data["records"][0],
    ]

    with pytest.raises(
        ValueError,
        match="중복된 신뢰 청크 UUID",
    ):
        authorized_hybrid_search.search_authorized_hybrid_context(
            "사건 질문",
            client=None,
            embedder=None,
            encoder=None,
            trusted_records=duplicate_records,
            documents=case_data["documents"],
            npc_cards=case_data["cards"],
            state=make_state(),
            evaluator=case_data["evaluator"],
        )

    search_mock.assert_not_called()


def test_different_case_state_rejected(case_data, monkeypatch):
    """게임 상태와 신뢰 청크의 사건 ID가 다르면 차단한다."""

    search_mock = mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    state = make_state().model_copy(update={"case_id": "CASE-999"})

    with pytest.raises(
        ValueError,
        match="사건 ID",
    ):
        run_authorized_search(
            case_data,
            state,
        )

    search_mock.assert_not_called()


def test_invalid_game_state_rejected(case_data, monkeypatch):
    """GameState가 아닌 입력은 검색 전에 차단한다."""

    search_mock = mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    with pytest.raises(
        TypeError,
        match="GameState",
    ):
        run_authorized_search(
            case_data,
            None,
        )

    search_mock.assert_not_called()


def test_forged_qdrant_payload_ignored(case_data, monkeypatch):
    """검색 후보에 가짜 본문이 있어도 서버 원본만 사용한다."""

    point_id = case_data["by_source"]["DOC-OPEN"]

    forged_candidate = SimpleNamespace(
        point_id=point_id,
        score=0.99,
        payload={
            "body": "FORGED SECRET CONTENT",
            "policy_id": "POL-FAKE",
            "access_scope": "public",
        },
    )

    monkeypatch.setattr(
        authorized_hybrid_search,
        "search_hybrid_candidates",
        Mock(return_value=[forged_candidate]),
    )

    results = run_authorized_search(
        case_data,
        make_state(),
    )

    assert len(results) == 1
    assert results[0].source_id == "DOC-OPEN"

    trusted_body = case_data["documents"][0].body

    assert results[0].content == trusted_body
    assert "FORGED SECRET CONTENT" not in results[0].content


def test_forged_policy_cannot_unlock_evidence(
    case_data,
    monkeypatch,
):
    """검색 결과의 정책을 위조해도 잠긴 문서는 공개되지 않는다."""

    point_id = case_data["by_source"]["DOC-LOCKED"]

    forged_candidate = SimpleNamespace(
        point_id=point_id,
        score=0.99,
        payload={
            "policy_id": "POL-DOC-OPEN",
            "required_evidence": [],
            "body": "FORGED PUBLIC CONTENT",
        },
    )

    monkeypatch.setattr(
        authorized_hybrid_search,
        "search_hybrid_candidates",
        Mock(return_value=[forged_candidate]),
    )

    results = run_authorized_search(
        case_data,
        make_state(),
    )

    assert results == []


def test_forged_npc_identity_cannot_cross_access(
    case_data,
    monkeypatch,
):
    """C02의 지식을 C01의 지식처럼 위장해도 차단한다."""

    point_id = case_data["by_source"]["K-C02-ONLY"]

    forged_candidate = SimpleNamespace(
        point_id=point_id,
        score=0.99,
        payload={
            "character_id": "C01",
            "source_type": "npc_knowledge",
        },
    )

    monkeypatch.setattr(
        authorized_hybrid_search,
        "search_hybrid_candidates",
        Mock(return_value=[forged_candidate]),
    )

    results = run_authorized_search(
        case_data,
        make_state(unlocked=["C01", "C02"]),
        active_character_id="C01",
    )

    assert results == []


def test_mixed_unknown_uuid_fails_closed(
    case_data,
    monkeypatch,
):
    """정상 UUID와 알 수 없는 UUID가 섞이면 요청을 거부한다."""

    valid_point_id = case_data["by_source"]["DOC-OPEN"]

    candidates = [
        HybridSearchCandidate(
            point_id=valid_point_id,
            score=0.95,
        ),
        HybridSearchCandidate(
            point_id="00000000-0000-4000-8000-000000000000",
            score=0.90,
        ),
    ]

    monkeypatch.setattr(
        authorized_hybrid_search,
        "search_hybrid_candidates",
        Mock(return_value=candidates),
    )

    with pytest.raises(
        ValueError,
        match="신뢰할 수 없는 검색 후보 UUID",
    ):
        run_authorized_search(
            case_data,
            make_state(),
        )


def test_tampered_trusted_body_rejected(
    case_data,
    monkeypatch,
):
    """원본 문서와 일치하지 않는 청크 본문을 차단한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    tampered_records = []

    for record in case_data["records"]:
        if record.chunk.source_id == "DOC-OPEN":
            forged_chunk = record.chunk.model_copy(
                update={
                    "body": "FORGED DOCUMENT BODY",
                }
            )

            record = replace(
                record,
                chunk=forged_chunk,
            )

        tampered_records.append(record)

    case_data["records"] = tampered_records

    with pytest.raises(
        ValueError,
        match="원본 청크 내용 불일치",
    ):
        run_authorized_search(
            case_data,
            make_state(),
        )


def test_tampered_trusted_policy_rejected(
    case_data,
    monkeypatch,
):
    """서버 원본과 다른 접근 정책 ID를 가진 청크를 차단한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    tampered_records = []

    for record in case_data["records"]:
        if record.chunk.source_id == "DOC-OPEN":
            forged_chunk = record.chunk.model_copy(
                update={
                    "policy_id": "POL-DOC-LOCKED",
                }
            )

            record = replace(
                record,
                chunk=forged_chunk,
            )

        tampered_records.append(record)

    case_data["records"] = tampered_records

    with pytest.raises(
        ValueError,
        match="메타데이터 불일치",
    ):
        run_authorized_search(
            case_data,
            make_state(),
        )


def test_tampered_npc_owner_rejected(
    case_data,
    monkeypatch,
):
    """신뢰 청크의 NPC 소유자 정보 변조를 차단한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "K-C01-OLD",
    )

    tampered_records = []

    for record in case_data["records"]:
        if record.chunk.source_id == "K-C01-OLD":
            forged_chunk = record.chunk.model_copy(
                update={
                    "character_id": "C02",
                }
            )

            record = replace(
                record,
                chunk=forged_chunk,
            )

        tampered_records.append(record)

    case_data["records"] = tampered_records

    with pytest.raises(
        ValueError,
        match="메타데이터 불일치",
    ):
        run_authorized_search(
            case_data,
            make_state(unlocked=["C01"]),
            active_character_id="C01",
        )


def test_missing_registered_policy_denies_access(
    case_data,
    monkeypatch,
):
    """등록되지 않은 정책은 기본적으로 접근을 거부한다."""

    mock_candidates(
        monkeypatch,
        case_data,
        "DOC-OPEN",
    )

    case_data["evaluator"] = PolicyEvaluator({})

    results = run_authorized_search(
        case_data,
        make_state(),
    )

    assert results == []
