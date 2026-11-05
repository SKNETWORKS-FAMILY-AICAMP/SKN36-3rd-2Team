import pytest
from pydantic import ValidationError

from crimescene.scenario.case_truth import CaseTruth


def make_truth_data():
    """테스트용 사건 진실 데이터를 생성한다."""

    return {
        "case_id": "CASE-TEST",
        "perpetrator_character_id": "NPC-TEST-001",
        "motive": "테스트용 범행 동기",
        "cause_of_death": "테스트용 사망 원인",
        "crime_method": "테스트용 범행 방법",
        "crime_event_id": "EVT-TEST-001",
        "related_event_ids": ["EVT-TEST-002"],
        "related_location_ids": ["LOC-TEST-001"],
        "related_evidence_ids": ["EVD-TEST-001"],
        "source_refs": [
            {
                "document_id": "DOC-TEST-001",
                "section": "1.2",
            }
        ],
    }


def test_case_truth_creation():
    """정상적인 사건 진실 원장을 생성한다."""

    truth = CaseTruth.model_validate(make_truth_data())

    assert truth.case_id == "CASE-TEST"
    assert truth.perpetrator_character_id == "NPC-TEST-001"
    assert truth.crime_event_id == "EVT-TEST-001"

    assert truth.related_event_ids == ["EVT-TEST-002"]
    assert truth.related_location_ids == ["LOC-TEST-001"]
    assert truth.related_evidence_ids == ["EVD-TEST-001"]

    assert truth.source_refs[0].document_id == "DOC-TEST-001"


def test_case_truth_default_access_scope():
    """진실 원장은 기본적으로 엔진 전용이다."""

    truth = CaseTruth.model_validate(make_truth_data())

    assert truth.access_scope == "ENGINE_ONLY"


def test_case_truth_missing_perpetrator():
    """범인 정보가 누락되면 오류가 발생한다."""

    data = make_truth_data()

    del data["perpetrator_character_id"]

    with pytest.raises(ValidationError):
        CaseTruth.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "case_id",
        "perpetrator_character_id",
        "motive",
        "cause_of_death",
        "crime_method",
        "crime_event_id",
    ],
)
def test_case_truth_empty_required_field(field):
    """필수 정보는 빈 문자열일 수 없다."""

    data = make_truth_data()

    data[field] = ""

    with pytest.raises(ValidationError):
        CaseTruth.model_validate(data)


def test_case_truth_unknown_field():
    """정의되지 않은 필드를 차단한다."""

    data = make_truth_data()

    data["unknown_field"] = "invalid"

    with pytest.raises(ValidationError):
        CaseTruth.model_validate(data)


def test_case_truth_public_access_rejected():
    """진실 원장을 공개 데이터로 지정할 수 없다."""

    data = make_truth_data()

    data["access_scope"] = "PUBLIC"

    with pytest.raises(ValidationError):
        CaseTruth.model_validate(data)


def test_case_truth_default_lists_independent():
    """서로 다른 진실 원장은 리스트를 공유하지 않는다."""

    data1 = make_truth_data()
    data2 = make_truth_data()

    data1["related_event_ids"] = []
    data2["related_event_ids"] = []

    truth1 = CaseTruth.model_validate(data1)
    truth2 = CaseTruth.model_validate(data2)

    truth1.related_event_ids.append("EVT-TEST-999")

    assert truth1.related_event_ids == ["EVT-TEST-999"]
    assert truth2.related_event_ids == []


def test_case_truth_invalid_source():
    """출처 문서 정보가 잘못되면 오류가 발생한다."""

    data = make_truth_data()

    data["source_refs"] = [
        {
            "document_id": "",
            "section": "1.2",
        }
    ]

    with pytest.raises(ValidationError):
        CaseTruth.model_validate(data)


def test_case_truth_json_roundtrip():
    """진실 원장을 JSON으로 변환하고 복원할 수 있다."""

    original = CaseTruth.model_validate(make_truth_data())

    json_data = original.model_dump_json()

    restored = CaseTruth.model_validate_json(json_data)

    assert restored == original
    assert restored.access_scope == "ENGINE_ONLY"
