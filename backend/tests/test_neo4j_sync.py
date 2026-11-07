"""Neo4j 동기화 변경사항 탐지 테스트."""

import pytest

from crimescene.db.neo4j_sync import (
    AREAS,
    build_sync_plan,
    compare_records,
)


def make_snapshot():
    """테스트용 그래프 스냅샷."""

    return {area: {} for area in AREAS}


def test_identical_data_no_changes():
    """동일 데이터의 반복 동기화는 변경사항이 없다."""

    expected = {"C01": {"label": "윤태식"}}
    actual = {"C01": {"label": "윤태식"}}

    delta = compare_records(expected, actual)

    assert delta.total_changes == 0
    assert delta.unchanged == ("C01",)


def test_new_entity_detected():
    """새로 추가된 엔티티를 탐지한다."""

    expected = {
        "C01": {"label": "윤태식"},
        "C02": {"label": "문지혜"},
    }

    actual = {
        "C01": {"label": "윤태식"},
    }

    delta = compare_records(expected, actual)

    assert delta.added == ("C02",)
    assert delta.updated == ()
    assert delta.deleted == ()


def test_modified_entity_detected():
    """이름이나 속성이 변경된 엔티티를 탐지한다."""

    expected = {"C01": {"label": "변경된 이름"}}
    actual = {"C01": {"label": "윤태식"}}

    delta = compare_records(expected, actual)

    assert delta.updated == ("C01",)


def test_deleted_entity_detected():
    """원본에서 제거된 엔티티를 탐지한다."""

    expected = {"C01": {"label": "윤태식"}}

    actual = {
        "C01": {"label": "윤태식"},
        "C02": {"label": "문지혜"},
    }

    delta = compare_records(expected, actual)

    assert delta.deleted == ("C02",)


def test_relationship_target_change_detected():
    """관계의 연결 대상이 변경되면 UPDATE로 분류한다."""

    expected = {
        "REL-001": {
            "source_id": "C01",
            "target_id": "C03",
        }
    }

    actual = {
        "REL-001": {
            "source_id": "C01",
            "target_id": "C02",
        }
    }

    delta = compare_records(expected, actual)

    assert delta.updated == ("REL-001",)


def test_admin_event_change_detected():
    """관리자 사건 내용 변경을 탐지한다."""

    expected = {
        "EVT-001": {
            "description": "수정된 사건 기록",
            "access_scope": "admin_only",
        }
    }

    actual = {
        "EVT-001": {
            "description": "기존 사건 기록",
            "access_scope": "admin_only",
        }
    }

    delta = compare_records(expected, actual)

    assert delta.updated == ("EVT-001",)


def test_extra_database_metadata_ignored():
    """원본에서 관리하지 않는 DB 속성은 변경 대상으로 보지 않는다."""

    expected = {"C01": {"label": "윤태식"}}

    actual = {
        "C01": {
            "label": "윤태식",
            "created_at": "2026-11-07",
        }
    }

    delta = compare_records(expected, actual)

    assert delta.total_changes == 0


def test_missing_field_detected():
    """필수 속성이 DB에 없다면 변경 대상으로 분류한다."""

    expected = {
        "C01": {
            "label": "윤태식",
            "entity_type": "Person",
        }
    }

    actual = {
        "C01": {
            "label": "윤태식",
        }
    }

    delta = compare_records(expected, actual)

    assert delta.updated == ("C01",)


def test_full_plan_counts_all_areas():
    """6개 그래프 영역의 변경사항을 합산한다."""

    expected = make_snapshot()
    actual = make_snapshot()

    expected["entities"] = {"C01": {"label": "윤태식"}}

    expected["relationships"] = {"REL-001": {"source_id": "C01"}}

    actual["entities"] = {"C01": {"label": "기존 이름"}}

    plan = build_sync_plan(expected, actual)

    assert len(plan.areas) == 6
    assert plan.total_changes == 2

    assert plan.areas["entities"].updated == ("C01",)
    assert plan.areas["relationships"].added == ("REL-001",)


def test_empty_snapshots_have_no_changes():
    """양쪽에 데이터가 없으면 변경사항이 없다."""

    expected = make_snapshot()
    actual = make_snapshot()

    plan = build_sync_plan(expected, actual)

    assert plan.total_changes == 0


@pytest.mark.parametrize(
    "area",
    AREAS,
)
def test_each_area_can_detect_additions(area):
    """모든 데이터 영역에서 신규 ID를 탐지한다."""

    expected = make_snapshot()
    actual = make_snapshot()

    expected[area] = {"TEST-001": {"value": "new"}}

    plan = build_sync_plan(expected, actual)

    assert plan.areas[area].added == ("TEST-001",)
