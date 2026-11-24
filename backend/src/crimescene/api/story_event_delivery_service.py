"""Retrieve and acknowledge player-authorized story events.

Only inject the trusted Django content client's approved-event fetcher.
These functions are internal services, not public HTTP endpoints.
"""

from collections.abc import Callable
from dataclasses import dataclass

from crimescene.api.django_content_client import ApprovedStoryEvent
from crimescene.api.story_event_delivery_gate import (
    StoryEventBinding,
    select_approved_queued_story_event,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

ApprovedEventFetcher = Callable[[str], ApprovedStoryEvent]


@dataclass(frozen=True)
class StoryEventAckResult:
    state: GameState
    created: bool


def _select_pending(
    state: GameState,
    binding: StoryEventBinding,
    fetch_approved_event: ApprovedEventFetcher,
) -> ApprovedStoryEvent | None:
    source_id = binding.source_story_id

    if source_id not in state.queued_story_events:
        return None

    if source_id in state.acknowledged_story_events:
        return None

    # This fetcher must call Django's approved internal API.
    # Never inject an object constructed from a player's request.
    approved = fetch_approved_event(binding.event_key)

    return select_approved_queued_story_event(
        state=state,
        binding=binding,
        approved_event=approved,
    )


def get_pending_story_event(
    repository: SQLiteCase001Repository,
    session_id: str,
    binding: StoryEventBinding,
    fetch_approved_event: ApprovedEventFetcher,
) -> ApprovedStoryEvent | None:
    """Read approved content without marking the event as consumed."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("SQLiteCase001Repository required")

    if not isinstance(binding, StoryEventBinding):
        raise TypeError("StoryEventBinding required")

    if not callable(fetch_approved_event):
        raise TypeError("Approved event fetcher required")

    state = repository.load_state(session_id)

    event = _select_pending(
        state,
        binding,
        fetch_approved_event,
    )

    # 외부 콘텐츠 조회 중 게임 상태가 변경됐는지 확인합니다.
    latest = repository.load_state(session_id)

    if latest != state:
        raise ValueError("GameState revision이 일치하지 않습니다.")

    return event


def acknowledge_story_event_atomic(
    repository: SQLiteCase001Repository,
    session_id: str,
    binding: StoryEventBinding,
    fetch_approved_event: ApprovedEventFetcher,
) -> StoryEventAckResult:
    """Persist an ACK exactly once using SQLite revision CAS."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("SQLiteCase001Repository required")

    if not isinstance(binding, StoryEventBinding):
        raise TypeError("StoryEventBinding required")

    if not callable(fetch_approved_event):
        raise TypeError("Approved event fetcher required")

    state = repository.load_state(session_id)
    source_id = binding.source_story_id

    if source_id in state.acknowledged_story_events:
        return StoryEventAckResult(state=state, created=False)

    approved = _select_pending(
        state,
        binding,
        fetch_approved_event,
    )

    if approved is None:
        raise PermissionError("Story event is not available for ACK")

    updated = GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            "acknowledged_story_events": [
                *state.acknowledged_story_events,
                source_id,
            ],
            "revision": state.revision + 1,
        }
    )

    try:
        saved = repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )
    except ValueError:
        # A concurrent ACK may have been committed first.
        latest = repository.load_state(session_id)

        if source_id in latest.acknowledged_story_events:
            return StoryEventAckResult(
                state=latest,
                created=False,
            )

        raise

    return StoryEventAckResult(
        state=saved,
        created=True,
    )
