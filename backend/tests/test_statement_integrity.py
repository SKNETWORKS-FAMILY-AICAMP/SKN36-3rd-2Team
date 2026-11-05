import pytest

from crimescene.scenario.models import CaseMetadata, TimelineEvent
from crimescene.scenario.npc_knowledge import (
    DisclosureCondition,
    DisclosureRule,
    KnowledgeType,
    NPCKnowledgeCard,
)
from crimescene.scenario.statement_assessment import StatementAssessment
from crimescene.scenario.statement_integrity import (
    validate_statement_references,
)


@pytest.fixture
def scenario_data():
    """테스트용 사건 및 NPC 진술 데이터."""

    case = CaseMetadata(
        case_id="CASE-TEST",
        title="테스트 사건",
        victim_name="신기범",
    )

    timeline = [
        TimelineEvent(
            event_id="EVT-001",
            description="첫 번째 테스트 사건",
        ),
        TimelineEvent(
            event_id="EVT-002",
            description="두 번째 테스트 사건",
        ),
    ]

    knowledge_cards = [
        NPCKnowledgeCard(
            knowledge_id="KNOW-001",
            npc_id="NPC-001",
            knowledge_type=KnowledgeType.OBSERVATION,
            content="첫 번째 NPC의 테스트 지식",
            disclosure_rule=DisclosureRule(
                condition=DisclosureCondition.OPEN,
            ),
        ),
        NPCKnowledgeCard(
            knowledge_id="KNOW-002",
            npc_id="NPC-002",
            knowledge_type=KnowledgeType.MEMORY,
            content="두 번째 NPC의 테스트 지식",
            disclosure_rule=DisclosureRule(
                condition=DisclosureCondition.OPEN,
            ),
        ),
    ]

    assessments = [
        StatementAssessment(
            assessment_id="ASM-001",
            case_id="CASE-TEST",
            npc_id="NPC-001",
            knowledge_id="KNOW-001",
            truth_status="TRUE",
            related_event_ids=["EVT-001"],
        ),
        StatementAssessment(
            assessment_id="ASM-002",
            case_id="CASE-TEST",
            npc_id="NPC-002",
            knowledge_id="KNOW-002",
            truth_status="FALSE",
            related_event_ids=["EVT-002"],
        ),
    ]

    return case, timeline, knowledge_cards, assessments


def validate(data, person_ids=("NPC-001", "NPC-002")):
    """테스트용 데이터 참조 검증."""

    case, timeline, knowledge_cards, assessments = data

    return validate_statement_references(
        case,
        timeline,
        knowledge_cards,
        assessments,
        person_ids=person_ids,
    )


def test_valid_statement_references(scenario_data):
    """정상적인 참조 관계는 오류가 없어야 한다."""

    errors = validate(scenario_data)

    assert errors == []


def test_duplicate_knowledge_id(scenario_data):
    """중복된 지식 카드 ID를 탐지한다."""

    cards = scenario_data[2]

    cards.append(cards[0].model_copy(deep=True))

    errors = validate(scenario_data)

    assert any(
        error.path == "knowledge_cards" and "중복" in error.message for error in errors
    )


def test_duplicate_assessment_id(scenario_data):
    """중복된 진술 평가 ID를 탐지한다."""

    assessments = scenario_data[3]

    assessments.append(assessments[0].model_copy(deep=True))

    errors = validate(scenario_data)

    assert any(
        error.path == "assessments" and "중복" in error.message for error in errors
    )


def test_missing_knowledge_reference(scenario_data):
    """존재하지 않는 지식 카드 참조를 탐지한다."""

    assessments = scenario_data[3]

    assessments[0].knowledge_id = "KNOW-999"

    errors = validate(scenario_data)

    assert any(error.path == "assessments[0].knowledge_id" for error in errors)


def test_knowledge_owner_mismatch(scenario_data):
    """진술자와 지식 소유자가 다르면 오류가 발생한다."""

    assessments = scenario_data[3]

    assessments[0].npc_id = "NPC-002"

    errors = validate(scenario_data)

    assert any(
        error.path == "assessments[0].npc_id" and "소유자" in error.message
        for error in errors
    )


def test_case_id_mismatch(scenario_data):
    """진술 평가의 사건 ID 불일치를 탐지한다."""

    assessments = scenario_data[3]

    assessments[0].case_id = "CASE-OTHER"

    errors = validate(scenario_data)

    assert any(error.path == "assessments[0].case_id" for error in errors)


def test_missing_timeline_reference(scenario_data):
    """존재하지 않는 타임라인 이벤트를 탐지한다."""

    assessments = scenario_data[3]

    assessments[0].related_event_ids = ["EVT-999"]

    errors = validate(scenario_data)

    assert any(error.path == "assessments[0].related_event_ids[0]" for error in errors)


def test_unknown_knowledge_npc(scenario_data):
    """지식 카드의 NPC가 인물 목록에 없으면 오류가 발생한다."""

    cards = scenario_data[2]

    cards[0].npc_id = "NPC-999"

    errors = validate(scenario_data)

    assert any(error.path == "knowledge_cards[0].npc_id" for error in errors)


def test_unknown_assessment_npc(scenario_data):
    """진술 평가의 NPC가 인물 목록에 없으면 오류가 발생한다."""

    assessments = scenario_data[3]

    assessments[0].npc_id = "NPC-999"

    errors = validate(scenario_data)

    assert any(
        error.path == "assessments[0].npc_id" and "존재하지 않는 NPC" in error.message
        for error in errors
    )


def test_optional_person_registry(scenario_data):
    """인물 목록이 없으면 NPC 존재 여부 검사를 생략한다."""

    cards = scenario_data[2]
    assessments = scenario_data[3]

    cards[0].npc_id = "NPC-999"
    assessments[0].npc_id = "NPC-999"

    errors = validate(scenario_data, person_ids=None)

    assert errors == []


def test_empty_person_registry(scenario_data):
    """빈 인물 목록은 검증 생략으로 처리하지 않는다."""

    errors = validate(scenario_data, person_ids=set())

    assert any("존재하지 않는 NPC" in error.message for error in errors)


def test_ambiguous_knowledge_owner(scenario_data):
    """중복 지식 ID의 소유자는 신뢰할 수 없어야 한다."""

    cards = scenario_data[2]

    duplicate = cards[0].model_copy(deep=True)
    duplicate.npc_id = "NPC-002"

    cards.append(duplicate)

    errors = validate(scenario_data)

    assert any(
        error.path == "assessments[0].knowledge_id"
        and "중복된 지식 카드" in error.message
        for error in errors
    )


def test_validation_does_not_modify_data(scenario_data):
    """무결성 검사는 원본 데이터를 변경하지 않는다."""

    case, timeline, cards, assessments = scenario_data

    before = (
        case.model_dump(),
        [event.model_dump() for event in timeline],
        [card.model_dump() for card in cards],
        [item.model_dump() for item in assessments],
    )

    validate(scenario_data)

    after = (
        case.model_dump(),
        [event.model_dump() for event in timeline],
        [card.model_dump() for card in cards],
        [item.model_dump() for item in assessments],
    )

    assert before == after
