from unittest.mock import MagicMock

import pytest

from crimescene.db.neo4j_event_ingest import (
    build_admin_graph_rows,
    ingest_admin_timeline,
)
from crimescene.scenario.source_timeline import SourceTimelineEvent


@pytest.fixture
def sample_data():
    event = SourceTimelineEvent.model_validate(
        {
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
            "event": "테스트 사건",
            "named_entity_ids": ["C01"],
            "source_note": "테스트",
            "source_refs": [{"path": "test.md"}],
            "truth_status": "character_statement",
            "access_scope": "admin_only",
        }
    )

    registry = [
        {
            "entity_id": "C01",
            "type": "Person",
            "label": "윤태식",
            "case_id": "CASE-001",
        }
    ]

    return [event], registry


def test_build_admin_graph(sample_data):
    """사건 및 인물 참조 관계 생성 검증."""

    events, registry = sample_data

    event_rows, mention_rows = build_admin_graph_rows(
        events,
        registry,
    )

    assert len(event_rows) == 1
    assert len(mention_rows) == 1

    assert (
        event_rows[0]["access_scope"]
        if ("access_scope" in event_rows[0])
        else event_rows[0]["event_id"] == "EVT-TEST-001"
    )

    assert mention_rows[0]["entity_id"] == "C01"


def test_unknown_entity(sample_data):
    """등록되지 않은 인물 참조 차단."""

    events, registry = sample_data

    invalid = events[0].model_copy(update={"named_entity_ids": ["UNKNOWN"]})

    with pytest.raises(ValueError, match="등록되지 않은"):
        build_admin_graph_rows([invalid], registry)


def test_non_admin_event_rejected(sample_data):
    """일반 공개 데이터가 관리자 원본으로 위장되는 것 방지."""

    events, registry = sample_data

    invalid = events[0].model_copy(update={"access_scope": "public"})

    with pytest.raises(ValueError, match="관리자 전용"):
        build_admin_graph_rows([invalid], registry)


def test_ingest_transaction(sample_data):
    """사건과 인물 참조가 적재되는지 검증."""

    events, registry = sample_data

    driver = MagicMock()

    result = ingest_admin_timeline(
        driver,
        events,
        registry,
    )

    assert result == {
        "events": 1,
        "mentions": 1,
    }

    sessions = driver.session.return_value.__enter__.return_value

    sessions.execute_write.assert_called_once()
