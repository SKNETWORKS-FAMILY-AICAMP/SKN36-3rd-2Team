from dataclasses import replace
from uuid import UUID

import pytest

from crimescene.ingest.chunking_config import ChunkingConfig, ChunkingMode
from crimescene.ingest.hybrid_access import build_authorized_hybrid_context
from crimescene.ingest.hybrid_chunker import build_hybrid_chunks
from crimescene.ingest.npc_knowledge_chunker import build_npc_knowledge_chunks
from crimescene.ingest.player_document_chunker import build_player_document_chunks
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import EvidenceState, GameState

CASE_ID = "CASE-001"

DOC_POLICY = "POL-CASE001-DOC-E01"
NPC_POLICY_1 = "POL-K-C01-01"
NPC_POLICY_2 = "POL-K-C02-01"
NPC_POLICY_3 = "POL-K-C01-02"

POINT_1 = "550e8400-e29b-41d4-a716-446655440000"
POINT_2 = "550e8400-e29b-41d4-a716-446655440001"
POINT_3 = "550e8400-e29b-41d4-a716-446655440002"
POINT_4 = "550e8400-e29b-41d4-a716-446655440003"


def make_policy(
    evidence=None,
    character_id=None,
):
    """테스트용 접근 정책."""

    return AccessPolicy(
        required_evidence=list(evidence or []),
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character=character_id,
    )


def make_policies():
    """테스트용 접근 정책 목록."""

    return {
        DOC_POLICY: make_policy(evidence=["E01"]),
        NPC_POLICY_1: make_policy(character_id="C01"),
        NPC_POLICY_2: make_policy(character_id="C02"),
        NPC_POLICY_3: make_policy(character_id="C01"),
    }


def make_document(body="테스트용 증거 문서입니다."):
    """플레이어 문서 생성."""

    return PlayerDocument(
        doc_id="DOC-001",
        case_id=CASE_ID,
        title="테스트 증거",
        body=body,
        family="evidence",
        access_scope="collected_evidence",
        truth_status="documented_in_game",
        source_evidence_ids=["E01"],
        known_by_character_ids=[],
        source_doc_ids=[],
        required_evidence=["E01"],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        protected_fact_ids=[],
        incident_year=2016,
        incident_years=[2016],
        source_refs=[],
        record_id="REC-001",
        point_id=POINT_1,
        policy_id=DOC_POLICY,
        state_version="7.1",
        content_version="1.0",
        build_id="test-build",
        content_hash="test-document-hash",
        search_text=body,
    )


def make_card(
    card_id,
    character_id,
    policy_id,
    point_id,
    *,
    supersedes=None,
):
    """NPC 지식 카드 생성."""

    return {
        "id": card_id,
        "case_id": CASE_ID,
        "character_id": character_id,
        "policy_id": policy_id,
        "body": f"{card_id} 테스트 진술",
        "search_text": f"{card_id} 테스트 진술",
        "family": "npc_knowledge",
        "access_scope": "character_only",
        "truth_status": "character_claim",
        "supersedes": list(supersedes or []),
        "stage_priority": 0,
        "required_evidence": [],
        "required_presentations": [],
        "required_flags": [],
        "required_ending": None,
        "required_topics": [],
        "required_disclosed_cards": [],
        "required_character": character_id,
        "point_id": point_id,
        "incident_year": 2016,
        "content_hash": "test-card-hash",
    }


def make_state(
    *,
    collected=True,
    unlocked=("C01", "C02"),
    case_id=CASE_ID,
):
    """테스트용 게임 진행 상태."""

    return GameState(
        case_id=case_id,
        session_id="TEST-SESSION",
        unlocked_characters=list(unlocked),
        evidence=({"E01": EvidenceState(stage="found")} if collected else {}),
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
    """테스트용 원본 및 Hybrid 청크."""

    document = make_document()

    cards = [
        make_card(
            "K-C01-01",
            "C01",
            NPC_POLICY_1,
            POINT_2,
        ),
        make_card(
            "K-C02-01",
            "C02",
            NPC_POLICY_2,
            POINT_3,
        ),
    ]

    policies = make_policies()

    document_chunks = build_player_document_chunks(
        [document],
        expected_case_id=CASE_ID,
        valid_policy_ids=set(policies),
    )

    npc_chunks = build_npc_knowledge_chunks(
        cards,
        expected_case_id=CASE_ID,
        valid_policy_ids=set(policies),
    )

    records = build_hybrid_chunks(
        document_chunks + npc_chunks,
        ChunkingConfig(mode=ChunkingMode.WHOLE),
    )

    return document, cards, policies, records


def authorize(
    records,
    case_data,
    *,
    state=None,
    active_character_id=None,
):
    """접근 권한 필터 호출."""

    document, cards, policies, _ = case_data

    if state is None:
        state = make_state()

    return build_authorized_hybrid_context(
        records,
        documents=[document],
        npc_cards=cards,
        state=state,
        evaluator=PolicyEvaluator(policies),
        active_character_id=active_character_id,
    )


def test_collected_document_allowed(case_data):
    """수집한 증거는 플레이어 조사 모드에서 허용."""

    record = case_data[3][0]

    result = authorize([record], case_data)

    assert len(result) == 1
    assert result[0].source_type == "player_document"
    assert result[0].source_id == "DOC-001"


def test_uncollected_document_blocked(case_data):
    """미수집 증거 차단."""

    record = case_data[3][0]

    result = authorize(
        [record],
        case_data,
        state=make_state(collected=False),
    )

    assert result == []


def test_unlocked_npc_allowed(case_data):
    """해금된 NPC의 지식 허용."""

    record = case_data[3][1]

    result = authorize(
        [record],
        case_data,
        active_character_id="C01",
    )

    assert len(result) == 1
    assert result[0].character_id == "C01"


def test_locked_npc_blocked(case_data):
    """미해금 NPC의 지식 차단."""

    record = case_data[3][1]

    result = authorize(
        [record],
        case_data,
        state=make_state(unlocked=()),
        active_character_id="C01",
    )

    assert result == []


def test_cross_npc_knowledge_blocked(case_data):
    """NPC A 대화 중 NPC B의 지식 차단."""

    npc_b_record = case_data[3][2]

    result = authorize(
        [npc_b_record],
        case_data,
        active_character_id="C01",
    )

    assert result == []


def test_player_document_blocked_in_npc_mode(case_data):
    """NPC 대화 모드에서 플레이어 문서 차단."""

    document_record = case_data[3][0]

    result = authorize(
        [document_record],
        case_data,
        active_character_id="C01",
    )

    assert result == []


def test_npc_knowledge_blocked_in_player_mode(case_data):
    """플레이어 조사 모드에서 NPC 지식 차단."""

    npc_record = case_data[3][1]

    result = authorize(
        [npc_record],
        case_data,
    )

    assert result == []


def test_superseded_statement_blocked(case_data):
    """새로운 진술이 공개되면 이전 진술 차단."""

    document, cards, policies, records = case_data

    new_card = make_card(
        "K-C01-02",
        "C01",
        NPC_POLICY_3,
        POINT_4,
        supersedes=["K-C01-01"],
    )

    result = build_authorized_hybrid_context(
        [records[1]],
        documents=[document],
        npc_cards=cards + [new_card],
        state=make_state(),
        evaluator=PolicyEvaluator(policies),
        active_character_id="C01",
    )

    # 새 진술은 전체 원본 목록에서 평가해야 합니다.
    # 검색 후보에 이전 진술만 있어도 차단해야 합니다.
    assert result == []


def test_forged_policy_id_rejected(case_data):
    """검색 결과의 정책 ID 위조 차단."""

    record = case_data[3][0]

    forged = replace(
        record,
        chunk=record.chunk.model_copy(update={"policy_id": "POL-FAKE"}),
    )

    with pytest.raises(
        ValueError,
        match="메타데이터 불일치",
    ):
        authorize([forged], case_data)


def test_forged_parent_uuid_rejected(case_data):
    """원본 Point ID 위조 차단."""

    record = case_data[3][0]

    forged = replace(
        record,
        parent_point_id=UUID(POINT_4),
    )

    with pytest.raises(
        ValueError,
        match="원본 Point ID 불일치",
    ):
        authorize([forged], case_data)


def test_forged_chunk_uuid_rejected(case_data):
    """청크 UUID 위조 차단."""

    record = case_data[3][0]

    forged = replace(
        record,
        chunk=record.chunk.model_copy(update={"chunk_id": UUID(POINT_4)}),
    )

    with pytest.raises(
        ValueError,
        match="청크 UUID 불일치",
    ):
        authorize([forged], case_data)


def test_forged_body_rejected(case_data):
    """검색 결과의 본문 변조 차단."""

    record = case_data[3][0]

    forged = replace(
        record,
        chunk=record.chunk.model_copy(update={"body": "조작된 사건 정보"}),
    )

    with pytest.raises(
        ValueError,
        match="원본 청크 내용 불일치",
    ):
        authorize([forged], case_data)


def test_duplicate_search_results_removed(case_data):
    """Dense/Sparse 검색 결과 중복 제거."""

    record = case_data[3][0]

    result = authorize(
        [record, record],
        case_data,
    )

    assert len(result) == 1


def test_other_case_document_blocked(case_data):
    """다른 사건의 문서 접근 차단."""

    record = case_data[3][0]

    result = authorize(
        [record],
        case_data,
        state=make_state(case_id="CASE-999"),
    )

    assert result == []


def test_forged_subchunk_rejected(case_data):
    """원본 일부를 임의로 잘라 만든 하위 청크 차단.

    단순 substring 검사로는 검증할 수 없는 상황입니다.
    """

    _document, cards, policies, _ = case_data

    long_text = "".join(f"{index:04d}" for index in range(460))

    long_document = make_document(body=long_text)

    source_chunks = build_player_document_chunks(
        [long_document],
        expected_case_id=CASE_ID,
        valid_policy_ids=set(policies),
    )

    records = build_hybrid_chunks(
        source_chunks,
        ChunkingConfig(mode=ChunkingMode.FIXED),
    )

    assert len(records) > 1

    record = records[1]

    # 원본에는 존재하지만 실제 청킹 결과와 다른 문자열
    forged_text = long_text[50:110]

    forged = replace(
        record,
        chunk=record.chunk.model_copy(
            update={
                "body": forged_text,
                "search_text": forged_text,
            }
        ),
    )

    with pytest.raises(
        ValueError,
        match="하위 청크 내용 불일치",
    ):
        build_authorized_hybrid_context(
            [forged],
            documents=[long_document],
            npc_cards=cards,
            state=make_state(),
            evaluator=PolicyEvaluator(policies),
        )


def make_long_case_data(case_data):
    """다중 청크 검증을 위한 긴 테스트 문서 생성."""

    _, cards, policies, _ = case_data

    long_text = "".join(f"{index:04d}" for index in range(460))

    document = make_document(body=long_text)

    source_chunks = build_player_document_chunks(
        [document],
        expected_case_id=CASE_ID,
        valid_policy_ids=set(policies),
    )

    records = build_hybrid_chunks(
        source_chunks,
        ChunkingConfig(mode=ChunkingMode.FIXED),
    )

    assert len(records) > 1

    return document, cards, policies, records


def authorize_long_chunks(
    records,
    case_data,
    *,
    trusted_records=None,
):
    """신뢰 청크 목록을 사용한 접근 검증."""

    document, cards, policies, _ = case_data

    return build_authorized_hybrid_context(
        records,
        documents=[document],
        npc_cards=cards,
        state=make_state(),
        evaluator=PolicyEvaluator(policies),
        trusted_records=trusted_records,
    )


def test_trusted_subchunks_allowed(case_data):
    """서버가 신뢰하는 정상 하위 청크는 허용한다."""

    data = make_long_case_data(case_data)

    _, _, _, records = data

    results = authorize_long_chunks(
        records,
        data,
        trusted_records=records,
    )

    assert len(results) == len(records)

    for result, record in zip(results, records, strict=True):
        assert result.source_id == record.chunk.source_id
        assert result.source_type == "player_document"
        assert result.content == record.chunk.body


def test_subchunks_without_trusted_records_blocked(case_data):
    """신뢰 목록이 없는 하위 청크는 차단한다."""

    data = make_long_case_data(case_data)

    _, _, _, records = data

    with pytest.raises(
        ValueError,
        match="신뢰 청크 없음",
    ):
        authorize_long_chunks(
            [records[1]],
            data,
        )


def test_tampered_subchunk_blocked_with_trusted_records(case_data):
    """정상 신뢰 목록이 있어도 변조된 본문은 차단한다."""

    data = make_long_case_data(case_data)

    document, _, _, records = data

    original_record = records[1]

    # 원본에 존재하지만 정상 청킹 결과와 다른 문자열
    forged_text = document.body[50:110]

    forged = replace(
        original_record,
        chunk=original_record.chunk.model_copy(
            update={
                "body": forged_text,
                "search_text": forged_text,
            }
        ),
    )

    with pytest.raises(
        ValueError,
        match="하위 청크 내용 불일치",
    ):
        authorize_long_chunks(
            [forged],
            data,
            trusted_records=records,
        )


def test_forged_chunk_count_blocked(case_data):
    """청크 개수 메타데이터 위조를 차단한다."""

    data = make_long_case_data(case_data)

    _, _, _, records = data

    original_record = records[1]

    forged = replace(
        original_record,
        chunk_count=original_record.chunk_count + 1,
    )

    with pytest.raises(
        ValueError,
        match="하위 청크 내용 불일치",
    ):
        authorize_long_chunks(
            [forged],
            data,
            trusted_records=records,
        )
