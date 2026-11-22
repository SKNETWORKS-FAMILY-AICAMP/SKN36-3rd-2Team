import pytest

from crimescene.api.django_content_client import ApprovedStoryEvent
from crimescene.api.story_event_delivery_gate import (
    StoryEventBinding,
    select_approved_queued_story_event,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import GamePhase, GameState


@pytest.fixture
def binding():
    return StoryEventBinding(
        source_story_id="STORY_020",
        event_key="EVT-CH01-901",
        chapter="CH01",
    )


@pytest.fixture
def approved_event():
    return ApprovedStoryEvent.model_construct(
        event_key="EVT-CH01-901",
        chapter="CH01",
        trigger_type="EVIDENCE_COLLECTED",
        required_evidence_ids=["E19"],
        title="TEST STORY",
        text="Approved test content.",
    )


@pytest.fixture
def state():
    initial = create_initial_state("delivery-test-session")

    return GameState.model_validate(
        {
            **initial.model_dump(mode="python"),
            "phase": GamePhase.INVESTIGATION,
            "current_chapter": "CH01",
            "unlocked_chapters": ["CH00", "CH01"],
            "evidence": {
                "E19": {"stage": "found"},
            },
            "flags": ["TEST_OFFICE_ACCESS_VERIFIED"],
            "queued_story_events": ["STORY_020"],
        }
    )


def test_approved_queued_event_can_be_selected(state, binding, approved_event):
    result = select_approved_queued_story_event(
        state=state,
        binding=binding,
        approved_event=approved_event,
    )
    assert result is approved_event


def test_event_not_in_queue_is_hidden(state, binding, approved_event):
    state.queued_story_events = []

    assert (
        select_approved_queued_story_event(
            state=state,
            binding=binding,
            approved_event=approved_event,
        )
        is None
    )


def test_wrong_event_key_is_hidden(state, binding, approved_event):
    approved_event.event_key = "EVT-CH01-902"

    assert (
        select_approved_queued_story_event(
            state=state,
            binding=binding,
            approved_event=approved_event,
        )
        is None
    )


def test_wrong_chapter_is_hidden(state, binding, approved_event):
    approved_event.chapter = "CH02"

    assert (
        select_approved_queued_story_event(
            state=state,
            binding=binding,
            approved_event=approved_event,
        )
        is None
    )


def test_missing_required_evidence_is_hidden(state, binding, approved_event):
    state.evidence = {}

    assert (
        select_approved_queued_story_event(
            state=state,
            binding=binding,
            approved_event=approved_event,
        )
        is None
    )


def test_finished_phase_is_denied(state, binding, approved_event):
    state.phase = GamePhase.FINISHED

    assert (
        select_approved_queued_story_event(
            state=state,
            binding=binding,
            approved_event=approved_event,
        )
        is None
    )


def test_other_case_is_denied(state, binding, approved_event):
    state.case_id = "OTHER-CASE"

    assert (
        select_approved_queued_story_event(
            state=state,
            binding=binding,
            approved_event=approved_event,
        )
        is None
    )


def test_unqueued_source_binding_is_denied(state, approved_event):
    other_binding = StoryEventBinding(
        source_story_id="STORY_019",
        event_key="EVT-CH01-901",
        chapter="CH01",
    )

    assert (
        select_approved_queued_story_event(
            state=state,
            binding=other_binding,
            approved_event=approved_event,
        )
        is None
    )


def test_mismatched_binding_chapter_rejected():
    with pytest.raises(ValueError):
        StoryEventBinding(
            source_story_id="STORY_020",
            event_key="EVT-CH02-901",
            chapter="CH01",
        )


def test_deep_ending_binding_rejected():
    with pytest.raises(ValueError):
        StoryEventBinding(
            source_story_id="STORY_030",
            event_key="EVT-CH04-901",
            chapter="CH04",
        )


def test_untrusted_event_type_rejected(state, binding):
    with pytest.raises(TypeError):
        select_approved_queued_story_event(
            state=state,
            binding=binding,
            approved_event={"event_key": "EVT-CH01-901"},
        )
