"""Server-side prerequisites for draft story events.

Passing this predicate does not authorize content publication.
Django approval and per-session disclosure checks remain mandatory.
"""

import re
from dataclasses import dataclass, field

from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)

EVIDENCE_ID_RE = re.compile(r"E(?:0[1-9]|[12][0-9]|30)")
STORY_ID_RE = re.compile(r"STORY_[0-9]{3}")
CHAPTER_RE = re.compile(r"CH0[0-4]")
FLAG_RE = re.compile(r"[A-Z][A-Z0-9_]{2,79}")

ACQUIRED_STAGES = frozenset({"found", "resolved"})


@dataclass(frozen=True)
class StoryEventConditions:
    """Trusted server-authored conditions for a story candidate."""

    story_id: str
    chapter: str
    all_evidence: frozenset[str] = field(default_factory=frozenset)
    any_evidence: frozenset[str] = field(default_factory=frozenset)
    required_flags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not STORY_ID_RE.fullmatch(self.story_id):
            raise ValueError("Invalid source story ID")

        if not CHAPTER_RE.fullmatch(self.chapter):
            raise ValueError("Invalid chapter")

        if self.story_id == "STORY_030":
            raise ValueError("Deep-ending event requires a separate consent gate")

        for collection in (self.all_evidence, self.any_evidence):
            if not isinstance(collection, frozenset):
                raise TypeError("Evidence conditions must be frozensets")

            if any(
                not isinstance(item, str) or not EVIDENCE_ID_RE.fullmatch(item)
                for item in collection
            ):
                raise ValueError("Invalid evidence ID")

        if not isinstance(self.required_flags, frozenset):
            raise TypeError("Required flags must be a frozenset")

        if any(
            not isinstance(item, str) or not FLAG_RE.fullmatch(item)
            for item in self.required_flags
        ):
            raise ValueError("Invalid server flag")

        # Current CASE-001 story candidates require an explicit
        # server-verified action, not evidence possession alone.
        if not self.required_flags:
            raise ValueError("A verified server action is required")


def matches_story_event_prerequisites(
    conditions: StoryEventConditions,
    state: GameState,
) -> bool:
    """Evaluate server-owned gameplay state without mutating it."""

    # STORY_026 requires the exact section-A inference contract.
    if conditions.story_id == "STORY_026":
        if (
            state.content_version != "case001_1120"
            or conditions.chapter != "CH03"
            or conditions.all_evidence != frozenset({"E20", "E26"})
            or conditions.any_evidence
            or conditions.required_flags != frozenset({
                "ACT_AUDIT_LOG_ACCESS_VERIFIED",
                "INF_POST_EVENT_DELETE",
            })
        ):
            return False

    if state.case_id != "CASE-001":
        return False

    if state.phase != GamePhase.INVESTIGATION:
        return False

    if state.outcome is not None:
        return False

    if (
        state.current_chapter != conditions.chapter
        or conditions.chapter not in state.unlocked_chapters
    ):
        return False

    acquired = {
        evidence_id
        for evidence_id, progress in state.evidence.items()
        if progress.stage in ACQUIRED_STAGES
    }

    if not conditions.all_evidence.issubset(acquired):
        return False

    if conditions.any_evidence and not conditions.any_evidence.intersection(acquired):
        return False

    return conditions.required_flags.issubset(set(state.flags))
