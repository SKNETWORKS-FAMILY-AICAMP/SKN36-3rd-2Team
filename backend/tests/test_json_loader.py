import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from crimescene.scenario.json_loader import (
    load_case_metadata,
    load_engine_timeline,
)


def write_json(
    directory: Path,
    filename: str,
    data: dict | list,
) -> Path:
    """테스트용 JSON 파일을 생성한다."""

    file_path = directory / filename

    file_path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )

    return file_path


def test_load_case_metadata(tmp_path):
    """정상적인 사건 기본 정보를 불러온다."""

    data = {
        "case_id": "CASE-001",
        "title": "마지막 기록: 사라진 공동체",
        "victim_name": "신기범",
    }

    file_path = write_json(
        tmp_path,
        "case_metadata.json",
        data,
    )

    result = load_case_metadata(file_path)

    assert result.case_id == "CASE-001"
    assert result.victim_name == "신기범"


def test_load_invalid_case_metadata(tmp_path):
    """필수 정보가 누락되면 오류가 발생한다."""

    data = {
        "case_id": "CASE-001",
        "title": "테스트 사건",
    }

    file_path = write_json(
        tmp_path,
        "invalid_case.json",
        data,
    )

    with pytest.raises(ValidationError):
        load_case_metadata(file_path)


def test_load_engine_timeline(tmp_path):
    """정상적인 타임라인을 불러온다."""

    data = [
        {
            "event_id": "EVT-001",
            "description": "첫 번째 테스트 사건",
            "started_at": "2026-10-17T20:00:00+09:00",
            "ended_at": "2026-10-17T20:10:00+09:00",
            "time_precision": "EXACT",
        },
        {
            "event_id": "EVT-002",
            "description": "두 번째 테스트 사건",
            "time_precision": "UNKNOWN",
        },
    ]

    file_path = write_json(
        tmp_path,
        "timeline.json",
        data,
    )

    result = load_engine_timeline(file_path)

    assert len(result) == 2
    assert result[0].event_id == "EVT-001"
    assert result[1].event_id == "EVT-002"
    assert result[0].access_scope == "ENGINE_ONLY"


def test_duplicate_event_id(tmp_path):
    """중복된 사건 ID를 차단한다."""

    data = [
        {
            "event_id": "EVT-001",
            "description": "첫 번째 사건",
        },
        {
            "event_id": "EVT-001",
            "description": "두 번째 사건",
        },
    ]

    file_path = write_json(
        tmp_path,
        "duplicate_timeline.json",
        data,
    )

    with pytest.raises(ValueError, match="중복"):
        load_engine_timeline(file_path)


def test_invalid_timeline_time(tmp_path):
    """시간 순서가 잘못된 사건을 차단한다."""

    data = [
        {
            "event_id": "EVT-001",
            "description": "시간 오류 테스트",
            "started_at": "2026-10-17T21:00:00+09:00",
            "ended_at": "2026-10-17T20:00:00+09:00",
        }
    ]

    file_path = write_json(
        tmp_path,
        "invalid_time.json",
        data,
    )

    with pytest.raises(ValidationError):
        load_engine_timeline(file_path)


def test_engine_timeline_access_restriction(tmp_path):
    """관리자 전용 데이터의 접근 범위를 검증한다."""

    data = [
        {
            "event_id": "EVT-001",
            "description": "비공개 사건",
            "access_scope": "PUBLIC",
        }
    ]

    file_path = write_json(
        tmp_path,
        "invalid_access.json",
        data,
    )

    with pytest.raises(ValidationError):
        load_engine_timeline(file_path)


def test_invalid_json_syntax(tmp_path):
    """잘못된 JSON 문법을 차단한다."""

    file_path = tmp_path / "broken.json"

    file_path.write_text(
        '{"case_id": "CASE-001", invalid}',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_case_metadata(file_path)


def test_missing_json_file(tmp_path):
    """존재하지 않는 파일을 읽으면 오류가 발생한다."""

    file_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        load_case_metadata(file_path)
