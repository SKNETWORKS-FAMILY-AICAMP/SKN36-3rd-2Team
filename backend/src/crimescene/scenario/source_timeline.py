from datetime import date, time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class SourceTimelineReference(BaseModel):
    """v7.1 타임라인의 원본 출처."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)

    section: str | None = None
    raw_time: str | None = None
    character_id: str | None = None


class SourceTimelineEvent(BaseModel):
    """v7.1 원본 타임라인 데이터 모델."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)

    incident_year: int
    year_start: int
    year_end: int

    date_start: date | None = None
    date_end: date | None = None

    time_start: time | None = None
    time_end: time | None = None

    temporal_precision: Literal[
        "second",
        "minute",
        "day",
        "part_of_day",
        "month",
        "year",
    ]

    raw_time: str = Field(min_length=1)
    event: str = Field(min_length=1)

    named_entity_ids: list[str] = Field(default_factory=list)

    source_note: str

    source_refs: list[SourceTimelineReference] = Field(min_length=1)

    truth_status: Literal[
        "admin_canonical",
        "character_statement",
    ]

    access_scope: Literal["admin_only"]


_timeline_adapter = TypeAdapter(list[SourceTimelineEvent])


def load_source_timeline(
    file_path: Path,
) -> list[SourceTimelineEvent]:
    """v7.1 원본 타임라인을 읽고 검증한다."""

    content = file_path.read_text(encoding="utf-8-sig")

    events = _timeline_adapter.validate_json(content)

    event_ids = [event.event_id for event in events]

    if len(event_ids) != len(set(event_ids)):
        raise ValueError("중복된 타임라인 이벤트 ID가 존재합니다.")

    return events
