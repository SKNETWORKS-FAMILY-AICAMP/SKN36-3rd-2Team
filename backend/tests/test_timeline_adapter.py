from datetime import date, datetime, time
from pathlib import Path

import pytest

from crimescene.scenario.models import EventTimePrecision
from crimescene.scenario.source_timeline import (
    SourceTimelineEvent,
    load_source_timeline,
)
from crimescene.scenario.timeline_adapter import (
    adapt_source_timeline,
    combine_event_datetime,
    convert_time_precision,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_source_event(**overrides):
    """테스트용 v7.1 타임라인 이벤트 생성."""

    data = {
        "event_id": "EVT-TEST-001",
        "case_id": "CASE-001",
        "incident_year": 2026,
        "year_start": 2026,
        "year_end": 2026,
        "date_start": "2026-10-17",
        "date_end": "2026-10-17",
        "time_start": "20:00:00",
        "time_end": "20:10:00",
        "temporal_precision": "second",
        "raw_time": "20:00~20:10",
        "event": "테스트용 사건",
        "named_entity_ids": ["C01"],
        "source_note": "테스트용 출처",
        "source_refs": [
            {
                "path": "admin/test.md",
                "section": "1.1",
            }
        ],
        "truth_status": "admin_canonical",
        "access_scope": "admin_only",
    }

    data.update(overrides)

    return SourceTimelineEvent.model_validate(data)


def test_combine_datetime():
    """날짜와 시간이 정확하게 결합되는지 확인."""

    result = combine_event_datetime(
        date(2026, 10, 17),
        time(20, 30),
    )

    assert result == datetime(2026, 10, 17, 20, 30)


def test_missing_time_not_invented():
    """날짜만 존재할 때 임의의 시간을 생성하지 않는다."""

    result = combine_event_datetime(
        date(2026, 10, 17),
        None,
    )

    assert result is None


def test_missing_date_not_invented():
    """시간만 존재할 때 임의의 날짜를 생성하지 않는다."""

    result = combine_event_datetime(
        None,
        time(20, 30),
    )

    assert result is None


@pytest.mark.parametrize(
    ("precision", "expected"),
    [
        ("second", EventTimePrecision.EXACT),
        ("minute", EventTimePrecision.APPROXIMATE),
        ("day", EventTimePrecision.UNKNOWN),
        ("part_of_day", EventTimePrecision.UNKNOWN),
        ("month", EventTimePrecision.UNKNOWN),
        ("year", EventTimePrecision.UNKNOWN),
    ],
)
def test_time_precision_conversion(precision, expected):
    """v7.1의 시간 정밀도를 기존 모델로 변환한다."""

    assert convert_time_precision(precision) == expected


def test_canonical_event_conversion():
    """관리자 확정 사실을 게임 엔진 이벤트로 변환한다."""

    source = make_source_event()

    result = adapt_source_timeline([source])

    assert len(result.engine_events) == 1
    assert len(result.statement_events) == 0

    event = result.engine_events[0]

    assert event.event_id == source.event_id
    assert event.description == source.event
    assert event.access_scope == "ENGINE_ONLY"

    assert event.started_at == datetime(2026, 10, 17, 20, 0)
    assert event.ended_at == datetime(2026, 10, 17, 20, 10)


def test_character_statement_separated():
    """인물 진술은 실제 사건 타임라인에 포함하지 않는다."""

    canonical = make_source_event()

    statement = make_source_event(
        event_id="EVT-TEST-002",
        truth_status="character_statement",
    )

    result = adapt_source_timeline([canonical, statement])

    assert len(result.source_events) == 2
    assert len(result.engine_events) == 1
    assert len(result.statement_events) == 1

    assert result.statement_events[0].event_id == "EVT-TEST-002"


def test_source_reference_preserved():
    """변환 후에도 원본 출처를 추적할 수 있다."""

    source = make_source_event()

    result = adapt_source_timeline([source])

    event = result.engine_events[0]

    assert len(event.source_refs) == 1
    assert event.source_refs[0].document_id == "admin/test.md"
    assert event.source_refs[0].section == "1.1"


def test_actor_ids_not_inferred():
    """언급된 인물을 실제 행동 인물로 임의 변환하지 않는다."""

    source = make_source_event(
        named_entity_ids=["C01", "C02"],
    )

    result = adapt_source_timeline([source])

    event = result.engine_events[0]

    assert event.actor_ids == []

    # 원본 정보는 유지한다.
    assert result.source_events[0].named_entity_ids == [
        "C01",
        "C02",
    ]


def test_partial_datetime_preserves_original():
    """불완전한 시각 정보는 원본에만 보존한다."""

    source = make_source_event(
        date_start=None,
        date_end=None,
        time_start=None,
        time_end=None,
        temporal_precision="year",
        raw_time="2026년",
    )

    result = adapt_source_timeline([source])

    engine_event = result.engine_events[0]

    assert engine_event.started_at is None
    assert engine_event.ended_at is None

    assert result.source_events[0].raw_time == "2026년"
    assert result.source_events[0].temporal_precision == "year"


def test_real_v71_timeline_adapter():
    """실제 v7.1 타임라인 전체를 검증한다."""

    root = PROJECT_ROOT / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/timeline_events.json"))

    if not matches:
        pytest.skip("로컬 v7.1 데이터가 없습니다.")

    assert len(matches) == 1

    source_events = load_source_timeline(matches[0])

    result = adapt_source_timeline(source_events)

    assert len(result.source_events) == 95
    assert len(result.engine_events) == 91
    assert len(result.statement_events) == 4

    assert all(event.access_scope == "ENGINE_ONLY" for event in result.engine_events)

    # 원본 이벤트와 변환된 이벤트 ID를 비교한다.
    canonical_ids = {
        event.event_id
        for event in source_events
        if event.truth_status == "admin_canonical"
    }

    engine_ids = {event.event_id for event in result.engine_events}

    assert canonical_ids == engine_ids
