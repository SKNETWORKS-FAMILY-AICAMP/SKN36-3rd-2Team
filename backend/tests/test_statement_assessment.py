import pytest
from pydantic import ValidationError

from crimescene.scenario.statement_assessment import (
    StatementAssessment,
    StatementIntent,
    StatementTruthStatus,
)


def make_assessment_data():
    """테스트용 NPC 진술 평가 데이터를 생성한다."""

    return {
        "assessment_id": "ASM-TEST-001",
        "case_id": "CASE-TEST",
        "npc_id": "NPC-TEST-001",
        "knowledge_id": "KNOW-TEST-001",
        "truth_status": "TRUE",
        "statement_intent": "HONEST",
        "related_event_ids": ["EVT-TEST-001"],
        "explanation": "테스트용 진술 평가 근거",
        "source_refs": [
            {
                "document_id": "DOC-TEST-001",
                "section": "1.1",
            }
        ],
    }


def test_statement_assessment_creation():
    """정상적인 진술 평가 데이터를 생성한다."""

    assessment = StatementAssessment.model_validate(make_assessment_data())

    assert assessment.assessment_id == "ASM-TEST-001"
    assert assessment.npc_id == "NPC-TEST-001"
    assert assessment.knowledge_id == "KNOW-TEST-001"

    assert assessment.truth_status == StatementTruthStatus.TRUE
    assert assessment.statement_intent == StatementIntent.HONEST

    assert assessment.access_scope == "ENGINE_ONLY"


@pytest.mark.parametrize(
    "truth_status",
    [
        StatementTruthStatus.TRUE,
        StatementTruthStatus.FALSE,
        StatementTruthStatus.PARTIALLY_TRUE,
        StatementTruthStatus.UNVERIFIED,
    ],
)
def test_valid_truth_status(truth_status):
    """모든 진술 사실 여부 유형을 허용한다."""

    data = make_assessment_data()
    data["truth_status"] = truth_status

    assessment = StatementAssessment.model_validate(data)

    assert assessment.truth_status == truth_status


@pytest.mark.parametrize(
    "intent",
    [
        StatementIntent.HONEST,
        StatementIntent.DECEPTIVE,
        StatementIntent.MISTAKEN,
        StatementIntent.UNKNOWN,
    ],
)
def test_valid_statement_intent(intent):
    """모든 진술 의도 유형을 허용한다."""

    data = make_assessment_data()
    data["statement_intent"] = intent

    assessment = StatementAssessment.model_validate(data)

    assert assessment.statement_intent == intent


def test_default_statement_intent():
    """진술 의도가 지정되지 않으면 UNKNOWN을 사용한다."""

    data = make_assessment_data()
    del data["statement_intent"]

    assessment = StatementAssessment.model_validate(data)

    assert assessment.statement_intent == StatementIntent.UNKNOWN


def test_missing_knowledge_id():
    """지식 카드 ID가 없으면 오류가 발생한다."""

    data = make_assessment_data()
    del data["knowledge_id"]

    with pytest.raises(ValidationError):
        StatementAssessment.model_validate(data)


def test_empty_npc_id():
    """NPC ID가 빈 문자열이면 오류가 발생한다."""

    data = make_assessment_data()
    data["npc_id"] = ""

    with pytest.raises(ValidationError):
        StatementAssessment.model_validate(data)


def test_unknown_field_rejected():
    """정의되지 않은 필드를 차단한다."""

    data = make_assessment_data()
    data["unknown_field"] = "invalid"

    with pytest.raises(ValidationError):
        StatementAssessment.model_validate(data)


def test_invalid_truth_status():
    """정의되지 않은 사실 여부를 차단한다."""

    data = make_assessment_data()
    data["truth_status"] = "MAYBE"

    with pytest.raises(ValidationError):
        StatementAssessment.model_validate(data)


def test_invalid_statement_intent():
    """정의되지 않은 진술 의도를 차단한다."""

    data = make_assessment_data()
    data["statement_intent"] = "INVALID"

    with pytest.raises(ValidationError):
        StatementAssessment.model_validate(data)


def test_engine_only_access():
    """진술 평가 데이터는 게임 엔진 전용이어야 한다."""

    data = make_assessment_data()
    data["access_scope"] = "PUBLIC"

    with pytest.raises(ValidationError):
        StatementAssessment.model_validate(data)


def test_invalid_source_reference():
    """잘못된 원본 문서 참조를 차단한다."""

    data = make_assessment_data()

    data["source_refs"] = [
        {
            "document_id": "",
            "section": "1.1",
        }
    ]

    with pytest.raises(ValidationError):
        StatementAssessment.model_validate(data)


def test_default_lists_independent():
    """서로 다른 평가 객체가 리스트를 공유하지 않는다."""

    data1 = make_assessment_data()
    data2 = make_assessment_data()

    data1["related_event_ids"] = []
    data2["related_event_ids"] = []

    assessment1 = StatementAssessment.model_validate(data1)
    assessment2 = StatementAssessment.model_validate(data2)

    assessment1.related_event_ids.append("EVT-TEST-999")

    assert assessment1.related_event_ids == ["EVT-TEST-999"]
    assert assessment2.related_event_ids == []


def test_statement_assessment_json_roundtrip():
    """진술 평가 데이터를 JSON으로 변환하고 복원한다."""

    original = StatementAssessment.model_validate(make_assessment_data())

    json_data = original.model_dump_json()

    restored = StatementAssessment.model_validate_json(json_data)

    assert restored == original
    assert restored.access_scope == "ENGINE_ONLY"
