import pytest

from crimescene.api.story_event_conditions import StoryEventConditions
from crimescene.api.story_event_queue import queue_story_event_atomic
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def repository(tmp_path):
    repo = SQLiteCase001Repository(tmp_path / "story_events.db")

    state = GameState(
        case_id="CASE-001",
        session_id="story-event-session",
        phase=GamePhase.INVESTIGATION,
        current_chapter="CH01",
        unlocked_chapters=["CH00", "CH01"],
        unlocked_characters=["C01"],
        evidence={"E19": EvidenceState(stage="found")},
        flags=["TEST_OFFICE_ACCESS_VERIFIED"],
        presented={},
        attempts_left=3,
        score=0,
        outcome=None,
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )

    repo.save_selection(state.session_id, "C01", state.revision)
    repo.register_state(state)

    return repo


@pytest.fixture
def conditions():
    return StoryEventConditions(
        story_id="STORY_020",
        chapter="CH01",
        all_evidence=frozenset({"E19"}),
        required_flags=frozenset(
            {
                "TEST_OFFICE_ACCESS_VERIFIED",
            }
        ),
    )


def test_first_queue_is_persisted(repository, conditions):
    result = queue_story_event_atomic(repository, "story-event-session", conditions)

    assert result.created is True
    assert result.state.revision == 1

    saved = repository.load_state("story-event-session")
    assert saved.queued_story_events == ["STORY_020"]
    assert saved.revision == 1


def test_retry_is_idempotent(repository, conditions):
    first = queue_story_event_atomic(repository, "story-event-session", conditions)
    second = queue_story_event_atomic(repository, "story-event-session", conditions)

    assert first.created is True
    assert second.created is False
    assert second.state.revision == 1
    assert second.state.queued_story_events == ["STORY_020"]


def test_missing_evidence_is_denied(repository):
    rule = StoryEventConditions(
        story_id="STORY_020",
        chapter="CH01",
        all_evidence=frozenset({"E20"}),
        required_flags=frozenset(
            {
                "TEST_OFFICE_ACCESS_VERIFIED",
            }
        ),
    )

    with pytest.raises(PermissionError):
        queue_story_event_atomic(repository, "story-event-session", rule)

    assert repository.load_state("story-event-session").revision == 0


def test_missing_action_is_denied(repository):
    rule = StoryEventConditions(
        story_id="STORY_020",
        chapter="CH01",
        all_evidence=frozenset({"E19"}),
        required_flags=frozenset({"TEST_UNVERIFIED_ACTION"}),
    )

    with pytest.raises(PermissionError):
        queue_story_event_atomic(repository, "story-event-session", rule)


def test_legacy_state_loads_without_queue(repository):
    saved = repository.load_state("story-event-session")
    legacy = saved.model_dump(mode="python")
    legacy.pop("queued_story_events")

    restored = GameState.model_validate(legacy)

    assert restored.queued_story_events == []


def test_duplicate_story_ids_are_rejected(repository):
    saved = repository.load_state("story-event-session")
    data = saved.model_dump(mode="python")
    data["queued_story_events"] = ["STORY_020", "STORY_020"]

    with pytest.raises(ValueError):
        GameState.model_validate(data)


def test_invalid_story_id_is_rejected(repository):
    saved = repository.load_state("story-event-session")
    data = saved.model_dump(mode="python")
    data["queued_story_events"] = ["INVALID"]

    with pytest.raises(ValueError):
        GameState.model_validate(data)


def test_concurrent_duplicate_commit_is_idempotent(repository, conditions, monkeypatch):
    original_commit = repository.commit_state

    def concurrent_commit(*, expected_state, updated_state):
        # Simulate another worker committing the same event first.
        original_commit(
            expected_state=expected_state,
            updated_state=updated_state,
        )
        raise ValueError("Simulated stale revision")

    monkeypatch.setattr(
        repository,
        "commit_state",
        concurrent_commit,
    )

    result = queue_story_event_atomic(repository, "story-event-session", conditions)

    assert result.created is False
    assert result.state.revision == 1
    assert result.state.queued_story_events == ["STORY_020"]


def test_unrelated_stale_revision_is_not_swallowed(repository, conditions, monkeypatch):
    original_commit = repository.commit_state

    def unrelated_commit(*, expected_state, updated_state):
        unrelated_state = GameState.model_validate(
            {
                **expected_state.model_dump(mode="python"),
                "flags": [
                    *expected_state.flags,
                    "TEST_OTHER_ACTION",
                ],
                "revision": expected_state.revision + 1,
            }
        )

        original_commit(
            expected_state=expected_state,
            updated_state=unrelated_state,
        )

        raise ValueError("Simulated unrelated stale revision")

    monkeypatch.setattr(
        repository,
        "commit_state",
        unrelated_commit,
    )

    with pytest.raises(ValueError):
        queue_story_event_atomic(repository, "story-event-session", conditions)

    saved = repository.load_state("story-event-session")
    assert saved.queued_story_events == []
    assert saved.revision == 1
