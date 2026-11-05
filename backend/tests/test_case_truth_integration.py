import json
from pathlib import Path

import pytest

from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.integrity import validate_case_references
from crimescene.scenario.json_loader import load_case_metadata
from crimescene.scenario.source_timeline import load_source_timeline
from crimescene.scenario.timeline_adapter import adapt_source_timeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"

SCENARIO_ROOT = BACKEND_ROOT / "data" / "scenario"
SOURCE_ROOT = PROJECT_ROOT / ".local" / "case001_v7_1"


def test_real_case_truth_integrity():
    """실제 사건 진실 원장과 타임라인의 참조 무결성을 검증한다."""

    truth_path = SCENARIO_ROOT / "engine_only" / "case_truth.json"

    # 비공개 원본이 없는 CI 환경에서는 건너뛴다.
    if not SOURCE_ROOT.is_dir() or not truth_path.is_file():
        pytest.skip("로컬 사건 원본이 없습니다.")

    timeline_paths = list(SOURCE_ROOT.glob("*/data/timeline_events.json"))
    registry_paths = list(SOURCE_ROOT.glob("*/data/entity_registry.json"))

    assert len(timeline_paths) == 1
    assert len(registry_paths) == 1

    case = load_case_metadata(SCENARIO_ROOT / "public" / "case_metadata.json")

    truth = CaseTruth.model_validate_json(truth_path.read_text(encoding="utf-8-sig"))

    source_events = load_source_timeline(timeline_paths[0])
    result = adapt_source_timeline(source_events)

    registry = json.loads(registry_paths[0].read_text(encoding="utf-8-sig"))

    person_ids = {item["entity_id"] for item in registry if item["type"] == "Person"}

    location_ids = {item["entity_id"] for item in registry if item["type"] == "Place"}

    errors = validate_case_references(
        case,
        truth,
        result.engine_events,
        person_ids=person_ids,
        location_ids=location_ids,
    )

    # 원본 데이터 개수 확인
    assert len(result.source_events) == 95
    assert len(result.engine_events) == 91
    assert len(result.statement_events) == 4

    # 범행 이벤트가 실제 타임라인에 존재하는지 확인
    event_ids = {event.event_id for event in result.engine_events}

    assert truth.crime_event_id in event_ids

    # 게임 엔진 전용 정보인지 확인
    assert truth.access_scope == "ENGINE_ONLY"

    # 참조 무결성 검증
    assert not errors, [f"{error.path}: {error.message}" for error in errors]
