from uuid import UUID

import pytest
from pydantic import ValidationError

from crimescene.ingest.npc_knowledge_chunker import (
    build_npc_knowledge_chunks,
)

CASE_ID = "CASE-001"

POLICY_1 = "POL-K-C01-01"
POLICY_2 = "POL-K-C02-01"

POINT_ID_1 = "550e8400-e29b-41d4-a716-446655440000"
POINT_ID_2 = "550e8400-e29b-41d4-a716-446655440001"


def make_card(
    card_id: str = "K-C01-01",
    character_id: str = "C01",
    point_id: str = POINT_ID_1,
    policy_id: str = POLICY_1,
    case_id: str = CASE_ID,
) -> dict[str, object]:
    """CASE-001 v7.1 형식의 테스트용 NPC 지식 카드."""

    return {
        "id": card_id,
        "case_id": case_id,
        "character_id": character_id,
        "policy_id": policy_id,
        "body": "NPC가 알고 있는 테스트 진술입니다.",
        "search_text": "NPC 사건 관련 검색용 텍스트",
        "family": "npc_knowledge",
        "access_scope": "character_only",
        "truth_status": "character_claim",
        "supersedes": [],
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
        "content_hash": "test-content-hash",
    }


def build_chunks(
    cards,
    *,
    expected_case_id: str = CASE_ID,
    valid_policy_ids: set[str] | None = None,
):
    """테스트용 NPC 청킹 함수 호출."""

    if valid_policy_ids is None:
        valid_policy_ids = {POLICY_1, POLICY_2}

    return build_npc_knowledge_chunks(
        cards,
        expected_case_id=expected_case_id,
        valid_policy_ids=valid_policy_ids,
    )


def test_valid_npc_card_chunk():
    """정상 NPC 카드가 청크로 변환되는지 확인."""

    card = make_card()

    chunks = build_chunks([card])

    assert len(chunks) == 1

    chunk = chunks[0]

    assert chunk.source_id == "K-C01-01"
    assert chunk.source_type == "npc_knowledge"
    assert chunk.character_id == "C01"
    assert chunk.case_id == CASE_ID
    assert chunk.policy_id == POLICY_1
    assert chunk.access_scope == "character_only"

    assert chunk.chunk_id == UUID(POINT_ID_1)
    assert chunk.point_id == POINT_ID_1

    assert chunk.body == card["body"]
    assert chunk.search_text == card["search_text"]


def test_multiple_npc_chunks():
    """서로 다른 NPC의 지식이 구분되는지 확인."""

    cards = [
        make_card(),
        make_card(
            card_id="K-C02-01",
            character_id="C02",
            point_id=POINT_ID_2,
            policy_id=POLICY_2,
        ),
    ]

    chunks = build_chunks(cards)

    assert len(chunks) == 2

    assert chunks[0].character_id == "C01"
    assert chunks[1].character_id == "C02"

    assert chunks[0].source_id != chunks[1].source_id
    assert chunks[0].chunk_id != chunks[1].chunk_id


def test_case_id_mismatch():
    """다른 사건의 지식 카드 혼입 차단."""

    card = make_card(case_id="CASE-999")

    with pytest.raises(
        ValueError,
        match="사건 ID 불일치",
    ):
        build_chunks([card])


def test_invalid_policy_reference():
    """등록되지 않은 접근 정책 차단."""

    card = make_card(policy_id="POL-UNKNOWN")

    with pytest.raises(
        ValueError,
        match="등록되지 않은 접근 정책",
    ):
        build_chunks([card])


def test_duplicate_card_id():
    """NPC 카드 ID 중복 차단."""

    cards = [
        make_card(),
        make_card(
            card_id="K-C01-01",
            point_id=POINT_ID_2,
        ),
    ]

    with pytest.raises(
        ValueError,
        match="중복 NPC 카드 ID",
    ):
        build_chunks(cards)


def test_duplicate_point_id():
    """Qdrant Point ID 중복 차단."""

    cards = [
        make_card(),
        make_card(
            card_id="K-C01-02",
            point_id=POINT_ID_1,
        ),
    ]

    with pytest.raises(
        ValueError,
        match="중복 Point ID",
    ):
        build_chunks(cards)


@pytest.mark.parametrize(
    "access_scope",
    [
        "collected_evidence",
        "conditional_record",
        "engine_only",
    ],
)
def test_invalid_npc_access_scope(access_scope: str):
    """NPC 전용이 아닌 접근 범위 차단."""

    card = make_card()
    card["access_scope"] = access_scope

    with pytest.raises(ValidationError):
        build_chunks([card])


@pytest.mark.parametrize(
    "character_id",
    [
        "",
        None,
        "   ",
    ],
)
def test_missing_character_id(character_id):
    """NPC 식별자가 비어 있으면 차단."""

    card = make_card()
    card["character_id"] = character_id

    with pytest.raises((ValidationError, ValueError)):
        build_chunks([card])


def test_required_character_mismatch():
    """카드 소유 NPC와 접근 조건 NPC가 다르면 차단."""

    card = make_card()
    card["required_character"] = "C02"

    with pytest.raises(
        ValueError,
        match="NPC 캐릭터 조건 불일치",
    ):
        build_chunks([card])


def test_invalid_point_id():
    """잘못된 UUID 차단."""

    card = make_card(point_id="invalid-uuid")

    with pytest.raises(ValidationError):
        build_chunks([card])


def test_missing_search_text():
    """검색 텍스트 누락 차단."""

    card = make_card()
    del card["search_text"]

    with pytest.raises(ValidationError):
        build_chunks([card])


def test_empty_cards():
    """빈 NPC 카드 목록 차단."""

    with pytest.raises(
        ValueError,
        match="청킹 대상 NPC 지식 카드가 없습니다",
    ):
        build_chunks([])


def test_empty_policy_catalog():
    """접근 정책 목록이 없으면 차단."""

    with pytest.raises(
        ValueError,
        match="접근 정책 목록이 비어 있습니다",
    ):
        build_chunks(
            [make_card()],
            valid_policy_ids=set(),
        )


def test_invalid_expected_case_id():
    """잘못된 사건 ID 차단."""

    with pytest.raises(
        ValueError,
        match="유효한 사건 ID",
    ):
        build_chunks(
            [make_card()],
            expected_case_id="",
        )


def test_invalid_card_type():
    """Mapping이 아닌 입력을 차단."""

    with pytest.raises(
        TypeError,
        match="Mapping 타입",
    ):
        build_chunks(["invalid-card"])


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "protected_fact_ids",
        "source_refs",
        "admin_truth",
        "effects",
    ],
)
def test_restricted_metadata_not_copied(forbidden_field: str):
    """민감한 내부 메타데이터를 청크에 복사하지 않는다."""

    card = make_card()

    card[forbidden_field] = "restricted-test-value"

    chunks = build_chunks([card])

    chunk_data = chunks[0].model_dump()

    assert forbidden_field not in chunk_data


def test_statement_progression_metadata_not_copied():
    """진술 대체 조건은 청크가 아닌 기존 엔진에서 처리한다."""

    card = make_card()

    card["supersedes"] = ["K-C01-00"]
    card["stage_priority"] = 10
    card["required_disclosed_cards"] = ["K-C01-00"]

    chunks = build_chunks([card])

    assert len(chunks) == 1

    chunk_data = chunks[0].model_dump()

    assert "supersedes" not in chunk_data
    assert "stage_priority" not in chunk_data
    assert "required_disclosed_cards" not in chunk_data

    # 원본 진술 데이터는 변경되지 않아야 한다.
    assert card["supersedes"] == ["K-C01-00"]
    assert card["stage_priority"] == 10
    assert card["required_disclosed_cards"] == ["K-C01-00"]
