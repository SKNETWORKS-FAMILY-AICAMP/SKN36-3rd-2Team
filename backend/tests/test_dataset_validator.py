import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from crimescene.scenario.dataset_validator import validate_scenario_data


def write_json(path: Path, data: object) -> None:
    """테스트용 JSON 파일 작성."""

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def scenario_root(tmp_path: Path) -> Path:
    """정상적인 테스트용 사건 데이터 폴더."""

    write_json(
        tmp_path / "public" / "case_metadata.json",
        {
            "case_id": "CASE-TEST",
            "title": "테스트 사건",
            "victim_name": "신기범",
        },
    )

    write_json(
        tmp_path / "engine_only" / "case_truth.json",
        {
            "case_id": "CASE-TEST",
            "perpetrator_character_id": "NPC-001",
            "motive": "테스트용 동기",
            "cause_of_death": "테스트용 사망 원인",
            "crime_method": "테스트용 범행 방법",
            "crime_event_id": "EVT-001",
            "related_event_ids": [],
            "related_location_ids": ["LOC-001"],
            "related_evidence_ids": ["EVD-001"],
        },
    )

    write_json(
        tmp_path / "engine_only" / "timeline.json",
        [
            {
                "event_id": "EVT-001",
                "description": "테스트 사건 발생",
                "actor_ids": ["NPC-001"],
                "location_ids": ["LOC-001"],
                "evidence_ids": ["EVD-001"],
            }
        ],
    )

    return tmp_path


def test_pending_when_all_files_missing(tmp_path):
    """필수 파일이 모두 없으면 PENDING."""

    report = validate_scenario_data(tmp_path)

    assert report.status == "PENDING"
    assert len(report.missing_files) == 3


def test_pending_when_private_files_missing(tmp_path):
    """진실 원장과 타임라인이 없으면 PENDING."""

    write_json(
        tmp_path / "public" / "case_metadata.json",
        {
            "case_id": "CASE-TEST",
            "title": "테스트 사건",
            "victim_name": "신기범",
        },
    )

    report = validate_scenario_data(tmp_path)

    assert report.status == "PENDING"
    assert "engine_only/case_truth.json" in report.missing_files
    assert "engine_only/timeline.json" in report.missing_files


def test_partial_without_reference_registry(scenario_root):
    """참조 ID 목록이 없으면 PARTIAL."""

    report = validate_scenario_data(scenario_root)

    assert report.status == "PARTIAL"
    assert report.event_count == 1
    assert len(report.unchecked_id_types) == 3


def test_valid_scenario(scenario_root):
    """모든 참조가 정상이면 VALID."""

    report = validate_scenario_data(
        scenario_root,
        person_ids={"NPC-001"},
        location_ids={"LOC-001"},
        evidence_ids={"EVD-001"},
    )

    assert report.status == "VALID"
    assert report.violations == ()
    assert report.unchecked_id_types == ()
    assert report.event_count == 1


def test_invalid_case_id(scenario_root):
    """사건 ID 불일치를 탐지한다."""

    path = scenario_root / "engine_only" / "case_truth.json"

    data = json.loads(path.read_text(encoding="utf-8"))
    data["case_id"] = "CASE-OTHER"

    write_json(path, data)

    report = validate_scenario_data(scenario_root)

    assert report.status == "INVALID"
    assert any(error.path == "case_id" for error in report.violations)


def test_invalid_crime_event(scenario_root):
    """존재하지 않는 범행 이벤트를 탐지한다."""

    path = scenario_root / "engine_only" / "case_truth.json"

    data = json.loads(path.read_text(encoding="utf-8"))
    data["crime_event_id"] = "EVT-999"

    write_json(path, data)

    report = validate_scenario_data(scenario_root)

    assert report.status == "INVALID"
    assert any(error.path == "truth.crime_event_id" for error in report.violations)


def test_invalid_timeline_actor(scenario_root):
    """존재하지 않는 인물 ID를 탐지한다."""

    path = scenario_root / "engine_only" / "timeline.json"

    data = json.loads(path.read_text(encoding="utf-8"))
    data[0]["actor_ids"] = ["NPC-999"]

    write_json(path, data)

    report = validate_scenario_data(
        scenario_root,
        person_ids={"NPC-001"},
        location_ids={"LOC-001"},
        evidence_ids={"EVD-001"},
    )

    assert report.status == "INVALID"
    assert any(error.path == "timeline[0].actor_ids[0]" for error in report.violations)


def test_empty_person_registry(scenario_root):
    """빈 인물 목록은 검증 생략으로 취급하지 않는다."""

    report = validate_scenario_data(
        scenario_root,
        person_ids=set(),
        location_ids={"LOC-001"},
        evidence_ids={"EVD-001"},
    )

    assert report.status == "INVALID"
    assert any(
        error.path == "truth.perpetrator_character_id" for error in report.violations
    )


def test_invalid_truth_data(scenario_root):
    """진실 원장 필수 정보 누락을 차단한다."""

    path = scenario_root / "engine_only" / "case_truth.json"

    write_json(
        path,
        {
            "case_id": "CASE-TEST",
        },
    )

    with pytest.raises(ValidationError):
        validate_scenario_data(scenario_root)


def test_duplicate_timeline_events(scenario_root):
    """중복 이벤트 ID를 허용하지 않는다."""

    path = scenario_root / "engine_only" / "timeline.json"

    data = json.loads(path.read_text(encoding="utf-8"))

    data.append(data[0].copy())

    write_json(path, data)

    with pytest.raises(ValueError, match="중복"):
        validate_scenario_data(scenario_root)
