import pytest

from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.integrity import validate_case_references
from crimescene.scenario.models import CaseMetadata, TimelineEvent


@pytest.fixture
def scenario_data():
    """테스트용 사건 데이터."""

    case = CaseMetadata(
        case_id="CASE-TEST",
        title="테스트 사건",
        victim_name="신기범",
    )

    truth = CaseTruth(
        case_id="CASE-TEST",
        perpetrator_character_id="NPC-001",
        motive="테스트용 동기",
        cause_of_death="테스트용 사망 원인",
        crime_method="테스트용 범행 방법",
        crime_event_id="EVT-002",
        related_event_ids=["EVT-001"],
        related_location_ids=["LOC-001"],
        related_evidence_ids=["EVD-001"],
    )

    timeline = [
        TimelineEvent(
            event_id="EVT-001",
            description="첫 번째 테스트 사건",
            actor_ids=["NPC-001"],
            location_ids=["LOC-001"],
            evidence_ids=["EVD-001"],
        ),
        TimelineEvent(
            event_id="EVT-002",
            description="두 번째 테스트 사건",
            actor_ids=["NPC-001"],
            location_ids=["LOC-001"],
        ),
    ]

    return case, truth, timeline


def validate(case, truth, timeline):
    """모든 참조 ID 목록을 사용해 검증."""

    return validate_case_references(
        case,
        truth,
        timeline,
        person_ids={"NPC-001"},
        location_ids={"LOC-001"},
        evidence_ids={"EVD-001"},
    )


def test_valid_case_references(scenario_data):
    """정상적인 사건 데이터는 오류가 없어야 한다."""

    case, truth, timeline = scenario_data

    errors = validate(case, truth, timeline)

    assert errors == []


def test_case_id_mismatch(scenario_data):
    """사건 ID 불일치를 탐지한다."""

    case, truth, timeline = scenario_data

    truth.case_id = "CASE-OTHER"

    errors = validate(case, truth, timeline)

    assert any(error.path == "case_id" for error in errors)


def test_duplicate_event_id(scenario_data):
    """중복된 타임라인 이벤트를 탐지한다."""

    case, truth, timeline = scenario_data

    timeline.append(timeline[0].model_copy(deep=True))

    errors = validate(case, truth, timeline)

    assert any("중복" in error.message for error in errors)


def test_missing_crime_event(scenario_data):
    """존재하지 않는 범행 이벤트를 탐지한다."""

    case, truth, timeline = scenario_data

    truth.crime_event_id = "EVT-999"

    errors = validate(case, truth, timeline)

    assert any(error.path == "truth.crime_event_id" for error in errors)


def test_missing_related_event(scenario_data):
    """존재하지 않는 관련 이벤트를 탐지한다."""

    case, truth, timeline = scenario_data

    truth.related_event_ids = ["EVT-999"]

    errors = validate(case, truth, timeline)

    assert any(error.path == "truth.related_event_ids[0]" for error in errors)


def test_missing_perpetrator(scenario_data):
    """범인 ID가 인물 목록에 존재하는지 확인한다."""

    case, truth, timeline = scenario_data

    truth.perpetrator_character_id = "NPC-999"

    errors = validate(case, truth, timeline)

    assert any(error.path == "truth.perpetrator_character_id" for error in errors)


def test_missing_truth_location(scenario_data):
    """진실 원장의 잘못된 장소 참조를 탐지한다."""

    case, truth, timeline = scenario_data

    truth.related_location_ids = ["LOC-999"]

    errors = validate(case, truth, timeline)

    assert any(error.path == "truth.related_location_ids[0]" for error in errors)


def test_missing_truth_evidence(scenario_data):
    """진실 원장의 잘못된 증거 참조를 탐지한다."""

    case, truth, timeline = scenario_data

    truth.related_evidence_ids = ["EVD-999"]

    errors = validate(case, truth, timeline)

    assert any(error.path == "truth.related_evidence_ids[0]" for error in errors)


@pytest.mark.parametrize(
    ("field_name", "invalid_id"),
    [
        ("actor_ids", "NPC-999"),
        ("location_ids", "LOC-999"),
        ("evidence_ids", "EVD-999"),
    ],
)
def test_invalid_timeline_references(
    scenario_data,
    field_name,
    invalid_id,
):
    """타임라인의 잘못된 인물·장소·증거 참조를 탐지한다."""

    case, truth, timeline = scenario_data

    setattr(timeline[0], field_name, [invalid_id])

    errors = validate(case, truth, timeline)

    expected_path = f"timeline[0].{field_name}[0]"

    assert any(error.path == expected_path for error in errors)


def test_optional_reference_lists(scenario_data):
    """ID 목록이 없으면 해당 참조 검사는 생략한다."""

    case, truth, timeline = scenario_data

    truth.perpetrator_character_id = "NPC-999"

    timeline[0].actor_ids = ["NPC-999"]

    errors = validate_case_references(
        case,
        truth,
        timeline,
    )

    assert errors == []


def test_validation_does_not_modify_data(scenario_data):
    """무결성 검사가 원본 데이터를 변경하지 않는다."""

    case, truth, timeline = scenario_data

    before = (
        case.model_dump(),
        truth.model_dump(),
        [event.model_dump() for event in timeline],
    )

    validate(case, truth, timeline)

    after = (
        case.model_dump(),
        truth.model_dump(),
        [event.model_dump() for event in timeline],
    )

    assert before == after
