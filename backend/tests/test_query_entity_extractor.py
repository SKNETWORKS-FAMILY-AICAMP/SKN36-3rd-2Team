"""CASE-001 자연어 엔티티 추출 테스트."""

import pytest

from crimescene.retriever.query_entity_extractor import (
    extract_question_entities,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GameState,
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


def make_state(*, unlocked=None, evidence=None):
    return GameState(
        case_id="CASE-001",
        session_id="GRAPH-ENTITY-TEST",
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


def extract(question, registry, state=None, **kwargs):
    return extract_question_entities(
        question,
        registry=registry,
        state=state or make_state(),
        **kwargs,
    )


def test_korean_name_with_particle(registry):
    """한국어 조사가 붙어도 이름을 식별한다."""

    result = extract("김서연이 무엇을 봤나요?", registry)

    assert [item.entity_id for item in result] == ["C01"]


def test_multiple_entities_in_question(registry):
    """질문에 등장한 순서대로 엔티티를 반환한다."""

    result = extract(
        "김서연은 세린국제학교에 있었나요?",
        registry,
        allowed_entity_ids={"P01"},
    )

    assert [item.entity_id for item in result] == [
        "C01",
        "P01",
    ]


def test_locked_character_hidden(registry):
    """미해금 NPC는 검색 대상에서 제외한다."""

    result = extract(
        "박민수는 누구인가요?",
        registry,
    )

    assert result == ()


def test_unlocked_character_found(registry):
    """해금된 NPC만 식별한다."""

    result = extract(
        "박민수는 누구인가요?",
        registry,
        make_state(unlocked=["C02"]),
    )

    assert [item.entity_id for item in result] == ["C02"]


def test_place_requires_explicit_permission(registry):
    """장소도 서버가 허용한 경우에만 식별한다."""

    result = extract(
        "세린국제학교에 있었나요?",
        registry,
    )

    assert result == ()


def test_unknown_entity_not_returned(registry):
    """원본에 없는 인물은 추측하지 않는다."""

    result = extract(
        "존재하지 않는 인물이 누구인가요?",
        registry,
    )

    assert result == ()


def test_partial_name_does_not_match(registry):
    """긴 이름의 일부분을 잘못 인식하지 않는다."""

    result = extract(
        "김서연수라는 사람을 아나요?",
        registry,
    )

    assert result == ()


def test_collected_evidence_found(registry):
    """수집한 증거 이름을 인식한다."""

    rule = EvidenceRule(
        name="목격자 진술서",
        score=10,
        holder="C01",
        prerequisites=[],
        presentation=[],
        q=[],
    )

    state = make_state(evidence={"E01": EvidenceState(stage="found")})

    result = extract(
        "목격자 진술서를 확인했나요?",
        registry,
        state,
        evidence_rules={"E01": rule},
    )

    assert [item.entity_id for item in result] == ["E01"]


def test_uncollected_evidence_hidden(registry):
    """미수집 증거는 이름을 입력해도 조회하지 않는다."""

    rule = EvidenceRule(
        name="목격자 진술서",
        score=10,
        holder="C01",
        prerequisites=[],
        presentation=[],
        q=[],
    )

    result = extract(
        "목격자 진술서를 확인했나요?",
        registry,
        evidence_rules={"E01": rule},
    )

    assert result == ()


def test_empty_question_rejected(registry):
    """빈 질문을 거부한다."""

    with pytest.raises(ValueError, match="비어 있습니다"):
        extract("  ", registry)


def test_duplicate_entity_id_rejected(registry):
    """원본 등록 정보의 중복 ID를 거부한다."""

    duplicated = [*registry, registry[0]]

    with pytest.raises(ValueError, match="중복"):
        extract("김서연", duplicated)


def test_invalid_limit_rejected(registry):
    """잘못된 엔티티 개수 제한을 거부한다."""

    with pytest.raises(ValueError, match="max_entities"):
        extract(
            "김서연",
            registry,
            max_entities=0,
        )


def test_custom_entity_type_requires_permission(registry):
    """원본의 추가 엔티티 유형도 권한을 검증한다."""

    custom_registry = [
        *registry,
        {
            "case_id": "CASE-001",
            "entity_id": "SERIN_SCHOOL",
            "type": "Institution",
            "label": "학교법인",
        },
    ]

    # 공개 권한이 없으면 검색되지 않아야 함
    blocked = extract(
        "SERIN_SCHOOL와 어떤 관계야?",
        custom_registry,
    )

    assert blocked == ()

    # 서버가 명시적으로 허용하면 검색 가능
    allowed = extract(
        "SERIN_SCHOOL와 어떤 관계야?",
        custom_registry,
        allowed_entity_ids={"SERIN_SCHOOL"},
    )

    assert [item.entity_id for item in allowed] == ["SERIN_SCHOOL"]
