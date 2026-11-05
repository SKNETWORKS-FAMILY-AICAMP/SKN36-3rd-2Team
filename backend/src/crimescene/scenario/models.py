from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EventTimePrecision(StrEnum):
    """사건 발생 시각의 정확도."""

    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    UNKNOWN = "UNKNOWN"


class SourceReference(BaseModel):
    """사건 정보의 원본 문서 참조."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    section: str | None = None


class CaseMetadata(BaseModel):
    """사건 기본 정보."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    victim_name: str = Field(min_length=1)
    schema_version: str = "1.0"


class TimelineEvent(BaseModel):
    """관리자 전용 실제 사건 타임라인."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)

    description: str = Field(min_length=1)

    started_at: datetime | None = None
    ended_at: datetime | None = None

    time_precision: EventTimePrecision = EventTimePrecision.UNKNOWN

    actor_ids: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    source_refs: list[SourceReference] = Field(default_factory=list)

    access_scope: Literal["ENGINE_ONLY"] = "ENGINE_ONLY"

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        """종료 시각이 시작 시각보다 빠르지 않은지 확인."""

        if self.started_at is not None and self.ended_at is not None:
            if self.started_at.tzinfo != self.ended_at.tzinfo:
                raise ValueError("시작과 종료 시각의 시간대가 일치해야 합니다.")

            if self.ended_at < self.started_at:
                raise ValueError("종료 시각은 시작 시각보다 빠를 수 없습니다.")

        return self
