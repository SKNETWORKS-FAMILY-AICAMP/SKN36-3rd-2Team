import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from crimescene.scenario.source_timeline import (
    SourceTimelineEvent,
    load_source_timeline,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_PATH = (
    PROJECT_ROOT
    / ".local"
    / "case001_v7_1"
    / "02_구조화_데이터"
    / "data"
    / "timeline_events.json"
)


def make_event():
    """테스트용 타임라인 데이터."""

    return {
        "event_id": "EVT-TEST-001",
        "case_id": "CASE-001",
        "incident_year": 2026,
        "year_start": 2026,
        "year_end": 2026,
        "date_start": "2026-10-17",
        "date_end": "2026-10-17",
        "time_start": "20:00",
        "time_end": "20:10",
        "temporal_precision": "minute",
        "raw_time": "20:00~20:10",
        "event": "테스트용 사건",
        "named_entity_ids": ["C01"],
        "source_note": "테스트 데이터",
        "source_refs": [
            {
                "path": "admin/test.md",
                "section": "1.1",
            }
        ],
        "truth_status": "admin_canonical",
        "access_scope": "admin_only",
    }


def test_valid_source_event():
    """정상적인 원본 이벤트 생성."""

    event = SourceTimelineEvent.model_validate(make_event())

    assert event.event_id == "EVT-TEST-001"
    assert event.case_id == "CASE-001"
    assert event.access_scope == "admin_only"


def test_invalid_access_scope():
    """관리자 전용 타임라인의 공개 설정을 차단."""

    data = make_event()
    data["access_scope"] = "PUBLIC"

    with pytest.raises(ValidationError):
        SourceTimelineEvent.model_validate(data)


def test_invalid_temporal_precision():
    """정의되지 않은 시간 정밀도 차단."""

    data = make_event()
    data["temporal_precision"] = "invalid"

    with pytest.raises(ValidationError):
        SourceTimelineEvent.model_validate(data)


def test_missing_source_reference():
    """출처가 없는 사건 데이터 차단."""

    data = make_event()
    data["source_refs"] = []

    with pytest.raises(ValidationError):
        SourceTimelineEvent.model_validate(data)


def test_duplicate_event_ids(tmp_path):
    """중복된 이벤트 ID 차단."""

    events = [make_event(), make_event()]

    path = tmp_path / "timeline.json"

    path.write_text(
        json.dumps(events, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="중복"):
        load_source_timeline(path)


def test_real_v71_timeline():
    """실제 v7.1 타임라인 95개 검증."""

    if not SOURCE_PATH.is_file():
        pytest.skip("로컬 v7.1 원본 데이터가 없습니다.")

    events = load_source_timeline(SOURCE_PATH)

    assert len(events) == 95

    # 사건 ID 검증
    assert all(event.case_id == "CASE-001" for event in events)

    # 이벤트 ID 중복 검사
    event_ids = [event.event_id for event in events]
    assert len(event_ids) == len(set(event_ids))

    # 관리자 전용 접근 등급 검사
    assert all(event.access_scope == "admin_only" for event in events)

    # 출처 정보 확인
    assert all(event.source_refs for event in events)

    # 사건 발생 연도 분포
    years = Counter(event.incident_year for event in events)

    assert years[2016] == 23
    assert years[2026] == 72

    # 관리자 확정 사실과 인물 진술 구분
    statuses = Counter(event.truth_status for event in events)

    assert statuses["admin_canonical"] == 91
    assert statuses["character_statement"] == 4
