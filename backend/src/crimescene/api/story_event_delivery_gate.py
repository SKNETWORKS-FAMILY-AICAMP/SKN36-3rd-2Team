"""Validate approved Django story content against player state."""

import re
from dataclasses import dataclass

from crimescene.api.django_content_client import ApprovedStoryEvent
from crimescene.api.story_event_gate import select_releasable_story_event
from crimescene.scenario.schemas.game_state import GamePhase, GameState

STORY_PATTERN = re.compile(r"STORY_[0-9]{3}")
EVENT_PATTERN = re.compile(r"EVT-CH0[0-4]-[0-9]{3}")
CHAPTER_PATTERN = re.compile(r"CH0[0-4]")


@dataclass(frozen=True)
class StoryEventBinding:
    """Explicit, trusted mapping approved by the backend."""

    source_story_id: str
    event_key: str
    chapter: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_story_id, str) or not STORY_PATTERN.fullmatch(
            self.source_story_id
        ):
            raise ValueError("Invalid source story ID")

        if not isinstance(self.chapter, str) or not CHAPTER_PATTERN.fullmatch(
            self.chapter
        ):
            raise ValueError("Invalid chapter")

        if (
            not isinstance(self.event_key, str)
            or not EVENT_PATTERN.fullmatch(self.event_key)
            or not self.event_key.startswith(f"EVT-{self.chapter}-")
        ):
            raise ValueError("Event key and chapter mismatch")

        if self.source_story_id == "STORY_030":
            raise ValueError("Deep-ending event requires a separate gate")


def select_approved_queued_story_event(
    *,
    state: GameState,
    binding: StoryEventBinding,
    approved_event: ApprovedStoryEvent,
) -> ApprovedStoryEvent | None:
    """Return content only after all player-state checks pass.

    approved_event must originate from the trusted Django content client.
    Do not construct it from user-supplied request data.
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState required")

    if not isinstance(binding, StoryEventBinding):
        raise TypeError("StoryEventBinding required")

    if not isinstance(approved_event, ApprovedStoryEvent):
        raise TypeError("ApprovedStoryEvent required")

    if state.case_id != "CASE-001":
        return None

    if state.phase != GamePhase.INVESTIGATION:
        return None

    if state.outcome is not None:
        return None

    if binding.source_story_id not in state.queued_story_events:
        return None

    if (
        binding.chapter != state.current_chapter
        or binding.chapter not in state.unlocked_chapters
    ):
        return None

    if (
        approved_event.event_key != binding.event_key
        or approved_event.chapter != binding.chapter
    ):
        return None

    # Reuse the existing server-side evidence and chapter policy.
    if not select_releasable_story_event(approved_event, state):
        return None

    return approved_event
