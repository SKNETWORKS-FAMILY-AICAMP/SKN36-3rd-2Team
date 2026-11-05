from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time

from crimescene.scenario.models import (
    EventTimePrecision,
    SourceReference,
    TimelineEvent,
)
from crimescene.scenario.source_timeline import SourceTimelineEvent


@dataclass(frozen=True, slots=True)
class TimelineAdapterResult:
    """타임라인 변환 결과."""

    engine_events: tuple[TimelineEvent, ...]
    statement_events: tuple[SourceTimelineEvent, ...]
    source_events: tuple[SourceTimelineEvent, ...]


def combine_event_datetime(
    event_date: date | None,
    event_time: time | None,
) -> datetime | None:
    """날짜와 시각이 모두 존재할 때만 datetime으로 변환한다."""

    if event_date is None or event_time is None:
        return None

    # 원본에 시간대가 명시되지 않았으므로 임의로 지정하지 않는다.
    return datetime.combine(event_date, event_time)


def convert_time_precision(
    precision: str,
) -> EventTimePrecision:
    """원본 시간 정밀도를 기존 게임 엔진 형식으로 변환한다."""

    if precision == "second":
        return EventTimePrecision.EXACT

    if precision == "minute":
        return EventTimePrecision.APPROXIMATE

    return EventTimePrecision.UNKNOWN


def adapt_source_timeline(
    source_events: Sequence[SourceTimelineEvent],
) -> TimelineAdapterResult:
    """v7.1 타임라인을 기존 게임 엔진 모델로 변환한다."""

    engine_events: list[TimelineEvent] = []
    statement_events: list[SourceTimelineEvent] = []

    for source in source_events:
        # 인물의 주장을 객관적 사실로 변환하지 않는다.
        if source.truth_status == "character_statement":
            statement_events.append(source)
            continue

        # 원본 날짜와 시각을 변환한다.
        started_at = combine_event_datetime(
            source.date_start,
            source.time_start,
        )

        ended_at = combine_event_datetime(
            source.date_end,
            source.time_end,
        )

        # 원본 출처를 게임 엔진 형식으로 변환한다.
        references = [
            SourceReference(
                document_id=ref.path,
                section=ref.section,
            )
            for ref in source.source_refs
        ]

        # 실제 사건 타임라인 생성
        event = TimelineEvent(
            event_id=source.event_id,
            description=source.event,
            started_at=started_at,
            ended_at=ended_at,
            time_precision=convert_time_precision(source.temporal_precision),
            source_refs=references,
            access_scope="ENGINE_ONLY",
        )

        engine_events.append(event)

    return TimelineAdapterResult(
        engine_events=tuple(engine_events),
        statement_events=tuple(statement_events),
        source_events=tuple(source_events),
    )
