"""Atomic, idempotent queueing of server-verified story candidates.

This module does not grant content publication permission.
Only trusted backend workflows may call it.
"""

from dataclasses import dataclass

from crimescene.api.story_event_conditions import (
    StoryEventConditions,
    matches_story_event_prerequisites,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@dataclass(frozen=True)
class StoryEventQueueResult:
    state: GameState
    created: bool


def queue_story_event_atomic(
    repository: SQLiteCase001Repository,
    session_id: str,
    conditions: StoryEventConditions,
) -> StoryEventQueueResult:
    """Record an eligible story ID once using SQLite revision CAS."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("SQLiteCase001Repository required")

    if not isinstance(conditions, StoryEventConditions):
        raise TypeError("StoryEventConditions required")

    state = repository.load_state(session_id)

    # A previously queued event remains available for recovery.
    if conditions.story_id in state.queued_story_events:
        return StoryEventQueueResult(state=state, created=False)

    if not matches_story_event_prerequisites(conditions, state):
        raise PermissionError("Story event prerequisites not satisfied")

    updated = GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            "queued_story_events": [
                *state.queued_story_events,
                conditions.story_id,
            ],
            "revision": state.revision + 1,
        }
    )

    try:
        committed = repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )
    except ValueError:
        # A concurrent request may already have queued the same event.
        # Only that case is treated as an idempotent retry.
        latest = repository.load_state(session_id)

        if conditions.story_id in latest.queued_story_events:
            return StoryEventQueueResult(
                state=latest,
                created=False,
            )

        raise

    return StoryEventQueueResult(
        state=committed,
        created=True,
    )
