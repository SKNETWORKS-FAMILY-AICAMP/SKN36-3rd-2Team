import json
from pathlib import Path
from uuid import UUID

import pytest

from crimescene.ingest.chunking_config import ChunkingConfig
from crimescene.ingest.hybrid_access import build_authorized_hybrid_context
from crimescene.ingest.hybrid_chunker import build_hybrid_chunks
from crimescene.ingest.npc_knowledge_chunker import (
    build_npc_knowledge_chunks,
)
from crimescene.ingest.player_document_chunker import (
    build_player_document_chunks,
)
from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.rag_access import build_authorized_rag_context
from crimescene.scenario.schemas.game_state import EvidenceState, GameState


@pytest.fixture(scope="module")
def case_chunks():
    """CASE-001 v7.1 원본 데이터 기반 통합 청킹."""

    root = Path(__file__).resolve().parents[2] / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/access_policies.json"))

    if not matches:
        pytest.skip("로컬 CASE-001 v7.1 데이터 없음")

    assert len(matches) == 1

    data_dir = matches[0].parent

    # 기존 검증 로더 재사용
    policies = load_access_policies(data_dir / "access_policies.json")

    documents = load_player_documents(data_dir / "player_documents.jsonl")

    # NPC JSONL 로딩
    cards = [
        json.loads(line)
        for line in (data_dir / "npc_knowledge_cards.jsonl")
        .read_text(encoding="utf-8-sig")
        .splitlines()
        if line.strip()
    ]

    valid_policy_ids = set(policies)

    # 플레이어 문서 청킹
    document_chunks = build_player_document_chunks(
        documents,
        expected_case_id="CASE-001",
        valid_policy_ids=valid_policy_ids,
    )

    # NPC 지식 카드 청킹
    npc_chunks = build_npc_knowledge_chunks(
        cards,
        expected_case_id="CASE-001",
        valid_policy_ids=valid_policy_ids,
    )

    return (
        policies,
        documents,
        cards,
        document_chunks,
        npc_chunks,
    )


def test_real_chunk_counts(case_chunks):
    """실제 데이터 116개가 모두 변환되는지 검증."""

    _, documents, cards, doc_chunks, npc_chunks = case_chunks

    assert len(documents) == 28
    assert len(cards) == 88

    assert len(doc_chunks) == 28
    assert len(npc_chunks) == 88

    assert len(doc_chunks) + len(npc_chunks) == 116


def test_global_point_id_uniqueness(case_chunks):
    """문서와 NPC 카드를 합쳐도 UUID 충돌이 없어야 한다."""

    _, documents, cards, doc_chunks, npc_chunks = case_chunks

    all_chunks = doc_chunks + npc_chunks

    point_ids = [chunk.point_id for chunk in all_chunks]

    assert len(point_ids) == 116
    assert len(set(point_ids)) == 116

    original_ids = {str(UUID(document.point_id)) for document in documents}

    original_ids.update(str(UUID(card["point_id"])) for card in cards)

    assert set(point_ids) == original_ids


def test_document_source_preserved(case_chunks):
    """플레이어 문서의 원본 식별자와 내용 보존."""

    _, documents, _, doc_chunks, _ = case_chunks

    originals = {document.doc_id: document for document in documents}

    for chunk in doc_chunks:
        original = originals[chunk.source_id]

        assert chunk.source_type == "player_document"
        assert chunk.policy_id == original.policy_id
        assert chunk.case_id == original.case_id
        assert chunk.content_hash == original.content_hash
        assert chunk.character_id is None

        if chunk.body != original.body:
            pytest.fail("플레이어 문서 본문 불일치")

        if chunk.search_text != original.search_text:
            pytest.fail("플레이어 문서 검색 텍스트 불일치")


def test_npc_source_preserved(case_chunks):
    """NPC 지식의 원본 및 캐릭터 정보 보존."""

    _, _, cards, _, npc_chunks = case_chunks

    originals = {card["id"]: card for card in cards}

    for chunk in npc_chunks:
        original = originals[chunk.source_id]

        assert chunk.source_type == "npc_knowledge"
        assert chunk.policy_id == original["policy_id"]
        assert chunk.case_id == original["case_id"]
        assert chunk.character_id == original["character_id"]
        assert chunk.content_hash == original["content_hash"]
        assert chunk.access_scope == "character_only"

        if chunk.body != original["body"]:
            pytest.fail("NPC 카드 본문 불일치")

        if chunk.search_text != original["search_text"]:
            pytest.fail("NPC 카드 검색 텍스트 불일치")


def test_all_policy_references_valid(case_chunks):
    """모든 청크의 접근 정책 참조 검증."""

    policies, _, _, doc_chunks, npc_chunks = case_chunks

    for chunk in doc_chunks + npc_chunks:
        assert chunk.policy_id in policies


def test_restricted_metadata_excluded(case_chunks):
    """내부 메타데이터가 청크에 포함되지 않는지 검증."""

    _, _, _, doc_chunks, npc_chunks = case_chunks

    expected_fields = {
        "chunk_id",
        "source_id",
        "source_type",
        "case_id",
        "policy_id",
        "family",
        "access_scope",
        "character_id",
        "incident_year",
        "content_hash",
        "search_text",
        "body",
    }

    for chunk in doc_chunks + npc_chunks:
        chunk_data = chunk.model_dump()

        assert set(chunk_data) == expected_fields

        assert "source_refs" not in chunk_data
        assert "protected_fact_ids" not in chunk_data
        assert "supersedes" not in chunk_data
        assert "stage_priority" not in chunk_data
        assert "effects" not in chunk_data


def test_real_hybrid_chunking_preserves_all_sources(case_chunks):
    """실제 116개 데이터의 Hybrid Chunking 무결성 검증."""

    policies, documents, cards, doc_chunks, npc_chunks = case_chunks

    # 1. 원본 RAG 청크 결합
    source_chunks = doc_chunks + npc_chunks

    assert len(documents) == 28
    assert len(cards) == 88
    assert len(source_chunks) == 116

    # 2. 원본 상태 기록
    original_data = [chunk.model_dump(mode="json") for chunk in source_chunks]

    # 3. Hybrid Chunking 실행
    config = ChunkingConfig()

    records = build_hybrid_chunks(
        source_chunks,
        config,
    )

    # 4. 전체 청크 개수 확인
    assert len(records) == 116

    # 5. UUID 중복 확인
    point_ids = [record.chunk.point_id for record in records]

    assert len(set(point_ids)) == 116

    # 6. 원본과 변환 결과 비교
    for source, record in zip(
        source_chunks,
        records,
        strict=True,
    ):
        chunk = record.chunk

        # 실제 데이터는 모두 짧으므로 원본 유지
        assert len(source.body) <= config.max_chunk_chars

        assert record.chunk_index == 0
        assert record.chunk_count == 1

        # UUID 보존
        assert record.parent_point_id == source.chunk_id
        assert chunk.chunk_id == source.chunk_id

        # 원본 식별자 및 정책 보존
        assert chunk.source_id == source.source_id
        assert chunk.source_type == source.source_type
        assert chunk.case_id == source.case_id
        assert chunk.policy_id == source.policy_id

        # NPC 지식 범위 보존
        assert chunk.character_id == source.character_id
        assert chunk.access_scope == source.access_scope

        # 원본 텍스트 보존
        assert chunk.body == source.body
        assert chunk.search_text == source.search_text
        assert chunk.content_hash == source.content_hash

        # 등록된 정책만 사용
        assert chunk.policy_id in policies

        # 내부 메타데이터 유입 방지
        chunk_data = chunk.model_dump()

        forbidden_fields = {
            "source_refs",
            "protected_fact_ids",
            "admin_truth",
            "supersedes",
            "stage_priority",
            "effects",
        }

        assert not forbidden_fields.intersection(chunk_data)

    # 7. 청킹 전후 원본이 변경되지 않았는지 확인
    assert [chunk.model_dump(mode="json") for chunk in source_chunks] == original_data


def test_real_hybrid_access_respects_game_state(case_chunks):
    """실제 CASE-001 데이터의 GameState 기반 접근 제어 검증."""

    policies, documents, cards, doc_chunks, npc_chunks = case_chunks

    # 1. 실제 116개 청크 생성
    source_chunks = doc_chunks + npc_chunks

    records = build_hybrid_chunks(
        source_chunks,
        ChunkingConfig(),
    )

    assert len(records) == 116

    # 2. 증거 수집 조건이 있는 플레이어 문서 선택
    document = next(
        (
            doc
            for doc in documents
            if doc.required_evidence or policies[doc.policy_id].required_evidence
        ),
        None,
    )

    assert document is not None

    policy = policies[document.policy_id]

    # 3. 문서 공개에 필요한 조건 구성
    evidence_ids = set(policy.required_evidence) | set(document.required_evidence)

    flags = set(policy.required_flags) | set(document.required_flags)

    presentations = set(policy.required_presentations) | set(
        document.required_presentations
    )

    presented: dict[str, list[str]] = {}

    for presentation in presentations:
        npc_id, separator, evidence_id = presentation.partition(":")

        assert separator
        assert npc_id
        assert evidence_id

        evidence_ids.add(evidence_id)
        presented.setdefault(npc_id, []).append(evidence_id)

    # 4. 필요한 조건을 충족하는 게임 상태 생성
    state = GameState(
        case_id="CASE-001",
        session_id="REAL-HYBRID-TEST",
        unlocked_characters=[],
        evidence={
            evidence_id: EvidenceState(stage="found") for evidence_id in evidence_ids
        },
        flags=sorted(flags),
        presented=presented,
        attempts_left=3,
        score=0,
        outcome=(policy.required_ending or document.required_ending or "ONGOING"),
        deep_eligible=False,
        revision=0,
        disclosed_cards=list(policy.required_disclosed_cards),
        document_grants=[],
    )

    evaluator = PolicyEvaluator(policies)

    topics = tuple(policy.required_topics)

    # 5. 기존 Issue #10 접근 엔진 결과
    expected = build_authorized_rag_context(
        documents=documents,
        npc_cards=cards,
        state=state,
        evaluator=evaluator,
        matched_topics=topics,
    )

    # 6. 새로운 Hybrid 접근 엔진 결과
    actual = build_authorized_hybrid_context(
        records,
        documents=documents,
        npc_cards=cards,
        state=state,
        evaluator=evaluator,
        matched_topics=topics,
    )

    # 7. 기존 엔진과 공개 결과 일치 확인
    assert [item.model_dump() for item in actual] == [
        item.model_dump() for item in expected
    ]

    # 선택한 문서는 정상적으로 접근 가능해야 함
    assert document.doc_id in {item.source_id for item in actual}

    # 플레이어 조사 모드에서 NPC 지식 차단
    assert all(item.source_type == "player_document" for item in actual)

    # 8. 증거 수집 기록 제거 후 접근 차단
    blocked_state = state.model_copy(
        update={"evidence": {}},
    )

    blocked_results = build_authorized_hybrid_context(
        records,
        documents=documents,
        npc_cards=cards,
        state=blocked_state,
        evaluator=evaluator,
        matched_topics=topics,
    )

    assert document.doc_id not in {item.source_id for item in blocked_results}

    # 9. 미해금 NPC 지식 접근 차단
    npc_id = cards[0]["character_id"]

    npc_results = build_authorized_hybrid_context(
        records,
        documents=documents,
        npc_cards=cards,
        state=state,
        evaluator=evaluator,
        active_character_id=npc_id,
    )

    assert npc_results == []
