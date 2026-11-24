"""Issue #147 - Story Event 큐 평가 및 보안 테스트."""

import pytest

from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
    ContentServiceNotFoundError,
)
from crimescene.api.story_event_conditions import (
    StoryEventConditions,
)
from crimescene.api.story_event_delivery_gate import (
    StoryEventBinding,
)
from crimescene.api.story_event_progress import (
    stage_story_events,
)
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)

EVENT_KEY = "EVT-CH01-001"
STORY_ID = "STORY_001"


@pytest.fixture
def state():
    return GameState(
        case_id="CASE-001",
        session_id="story-progress-test",
        phase=GamePhase.INVESTIGATION,
        current_chapter="CH01",
        unlocked_chapters=["CH00", "CH01"],
        unlocked_characters=["C01"],
        evidence={
            "E01": EvidenceState(stage="found"),
        },
        flags=["TEST_VERIFIED_ACTION"],
        presented={},
        attempts_left=3,
        score=1,
        outcome=None,
        deep_eligible=False,
        revision=5,
        disclosed_cards=[],
        document_grants=[],
    )


@pytest.fixture
def bindings():
    return {
        EVENT_KEY: StoryEventBinding(
            source_story_id=STORY_ID,
            event_key=EVENT_KEY,
            chapter="CH01",
        ),
    }


@pytest.fixture
def conditions():
    return {
        STORY_ID: StoryEventConditions(
            story_id=STORY_ID,
            chapter="CH01",
            all_evidence=frozenset({"E01"}),
            required_flags=frozenset(
                {"TEST_VERIFIED_ACTION"}
            ),
        ),
    }


def fetch_approved(event_key):
    return ApprovedStoryEvent(
        event_key=event_key,
        chapter="CH01",
        trigger_type="EVIDENCE_COLLECTED",
        required_evidence_ids=["E01"],
        title="Test event",
        text="Approved test content",
    )


def unexpected_fetch(event_key):
    pytest.fail(f"Unexpected Django request: {event_key}")


def test_approved_event_is_staged(
    state,
    bindings,
    conditions,
):
    updated = stage_story_events(
        state,
        bindings=bindings,
        conditions=conditions,
        fetch_approved_event=fetch_approved,
    )

    assert updated.queued_story_events == [STORY_ID]
    assert updated.revision == state.revision
    assert state.queued_story_events == []


def test_duplicate_event_is_not_staged(
    state,
    bindings,
    conditions,
):
    first = stage_story_events(
        state,
        bindings=bindings,
        conditions=conditions,
        fetch_approved_event=fetch_approved,
    )

    second = stage_story_events(
        first,
        bindings=bindings,
        conditions=conditions,
        fetch_approved_event=unexpected_fetch,
    )

    assert second == first
    assert second.queued_story_events == [STORY_ID]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence", {}),
        ("flags", []),
        ("current_chapter", "CH00"),
        ("phase", GamePhase.FINISHED),
        ("outcome", "SUCCESS"),
        ("case_id", "CASE-999"),
    ],
)
def test_ineligible_state_is_not_staged(
    state,
    bindings,
    conditions,
    field,
    value,
):
    blocked = GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            field: value,
        }
    )

    updated = stage_story_events(
        blocked,
        bindings=bindings,
        conditions=conditions,
        fetch_approved_event=unexpected_fetch,
    )

    assert updated == blocked
    assert updated.queued_story_events == []


def test_unapproved_event_is_not_staged(
    state,
    bindings,
    conditions,
):
    def fetch(event_key):
        raise ContentServiceNotFoundError(
            "Not approved"
        )

    updated = stage_story_events(
        state,
        bindings=bindings,
        conditions=conditions,
        fetch_approved_event=fetch,
    )

    assert updated == state


def test_django_failure_preserves_original_state(
    state,
    bindings,
    conditions,
):
    def fetch(event_key):
        raise ContentServiceError("Unavailable")

    with pytest.raises(ContentServiceError):
        stage_story_events(
            state,
            bindings=bindings,
            conditions=conditions,
            fetch_approved_event=fetch,
        )

    assert state.queued_story_events == []
    assert state.revision == 5


def test_django_evidence_requirement_is_enforced(
    state,
    bindings,
    conditions,
):
    def fetch(event_key):
        return ApprovedStoryEvent(
            event_key=event_key,
            chapter="CH01",
            trigger_type="EVIDENCE_COLLECTED",
            required_evidence_ids=["E02"],
            title="Test event",
            text="Restricted content",
        )

    updated = stage_story_events(
        state,
        bindings=bindings,
        conditions=conditions,
        fetch_approved_event=fetch,
    )

    assert updated == state


def test_missing_conditions_are_rejected(
    state,
    bindings,
):
    with pytest.raises(ValueError):
        stage_story_events(
            state,
            bindings=bindings,
            conditions={},
            fetch_approved_event=unexpected_fetch,
        )


def test_empty_configuration_is_safe(state):
    updated = stage_story_events(
        state,
        bindings={},
        conditions={},
        fetch_approved_event=unexpected_fetch,
    )

    assert updated == state