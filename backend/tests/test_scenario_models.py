from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from crimescene.scenario.models import (
    CaseMetadata,
    EventTimePrecision,
    TimelineEvent,
)


def test_case_metadata_creation():
    """사건 기본 정보가 정상적으로 생성되는지 확인."""

    case = CaseMetadata(
        case_id="CASE-001",
        title="마지막 기록: 사라진 공동체",
        victim_name="신기범",
    )

    assert case.case_id == "CASE-001"
    assert case.victim_name == "신기범"
    assert case.schema_version == "1.0"


def test_case_metadata_empty_id():
    """사건 ID가 비어 있으면 오류가 발생해야 한다."""

    with pytest.raises(ValidationError):
        CaseMetadata(
            case_id="",
            title="테스트 사건",
            victim_name="신기범",
        )


def test_case_metadata_unknown_field():
    """정의되지 않은 필드는 허용하지 않는다."""

    with pytest.raises(ValidationError):
        CaseMetadata.model_validate(
            {
                "case_id": "CASE-001",
                "title": "테스트 사건",
                "victim_name": "신기범",
                "unknown_field": "invalid",
            }
        )


def test_timeline_event_creation():
    """정상적인 사건 타임라인을 생성할 수 있어야 한다."""

    event = TimelineEvent(
        event_id="EVT-001",
        description="테스트 사건 발생",
        started_at=datetime(2026, 10, 17, 20, 0),
        ended_at=datetime(2026, 10, 17, 20, 10),
        time_precision=EventTimePrecision.EXACT,
        actor_ids=["NPC-001"],
        location_ids=["LOC-001"],
        evidence_ids=["EVD-001"],
    )

    assert event.event_id == "EVT-001"
    assert event.access_scope == "ENGINE_ONLY"
    assert event.actor_ids == ["NPC-001"]
    assert event.time_precision == EventTimePrecision.EXACT


def test_timeline_invalid_time_range():
    """종료 시각이 시작 시각보다 빠르면 오류가 발생해야 한다."""

    with pytest.raises(ValidationError):
        TimelineEvent(
            event_id="EVT-002",
            description="잘못된 시간 순서",
            started_at=datetime(2026, 10, 17, 21, 0),
            ended_at=datetime(2026, 10, 17, 20, 0),
        )


def test_timeline_timezone_mismatch():
    """시작과 종료 시각의 시간대 설정이 다르면 오류가 발생한다."""

    with pytest.raises(ValidationError):
        TimelineEvent(
            event_id="EVT-003",
            description="시간대 불일치",
            started_at=datetime(2026, 10, 17, 20, 0),
            ended_at=datetime(2026, 10, 17, 21, 0, tzinfo=UTC),
        )


def test_timeline_access_scope_restriction():
    """실제 사건 타임라인은 ENGINE_ONLY만 허용한다."""

    with pytest.raises(ValidationError):
        TimelineEvent.model_validate(
            {
                "event_id": "EVT-004",
                "description": "비공개 사건 정보",
                "access_scope": "PUBLIC",
            }
        )


def test_timeline_default_lists_are_independent():
    """서로 다른 사건 객체가 동일한 리스트를 공유하면 안 된다."""

    event1 = TimelineEvent(
        event_id="EVT-005",
        description="첫 번째 사건",
    )

    event2 = TimelineEvent(
        event_id="EVT-006",
        description="두 번째 사건",
    )

    event1.actor_ids.append("NPC-001")

    assert event1.actor_ids == ["NPC-001"]
    assert event2.actor_ids == []
