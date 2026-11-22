import pytest

from crimescene.api.django_content_client import ApprovedStoryEvent
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.api.story_event_delivery_service import (
    acknowledge_story_event_atomic,
    get_pending_story_event,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def repository(tmp_path):
    repo = SQLiteCase001Repository(tmp_path / "story_delivery.db")
    initial = create_initial_state("delivery-session")

    state = GameState.model_validate(
        {
            **initial.model_dump(mode="python"),
            "phase": GamePhase.INVESTIGATION,
            "current_chapter": "CH01",
            "unlocked_chapters": ["CH00", "CH01"],
            "evidence": {"E19": {"stage": "found"}},
            "queued_story_events": ["STORY_020"],
        }
    )

    repo.save_selection(state.session_id, "C01", state.revision)
    repo.register_state(state)
    return repo


@pytest.fixture
def binding():
    return StoryEventBinding(
        source_story_id="STORY_020",
        event_key="EVT-CH01-901",
        chapter="CH01",
    )


@pytest.fixture
def fetch_approved():
    event = ApprovedStoryEvent.model_construct(
        event_key="EVT-CH01-901",
        chapter="CH01",
        trigger_type="EVIDENCE_COLLECTED",
        required_evidence_ids=["E19"],
        title="TEST STORY",
        text="Test content only.",
    )

    def fetch(event_key):
        assert event_key == "EVT-CH01-901"
        return event

    return fetch


def test_pending_event_is_returned(repository, binding, fetch_approved):
    result = get_pending_story_event(
        repository,
        "delivery-session",
        binding,
        fetch_approved,
    )

    assert result is not None
    assert result.event_key == "EVT-CH01-901"
    assert repository.load_state("delivery-session").revision == 0


def test_ack_is_persisted(repository, binding, fetch_approved):
    result = acknowledge_story_event_atomic(
        repository,
        "delivery-session",
        binding,
        fetch_approved,
    )

    assert result.created is True
    assert result.state.revision == 1
    assert result.state.acknowledged_story_events == ["STORY_020"]

    saved = repository.load_state("delivery-session")
    assert saved.acknowledged_story_events == ["STORY_020"]


def test_ack_retry_is_idempotent(repository, binding, fetch_approved):
    first = acknowledge_story_event_atomic(
        repository, "delivery-session", binding, fetch_approved
    )
    second = acknowledge_story_event_atomic(
        repository, "delivery-session", binding, fetch_approved
    )

    assert first.created is True
    assert second.created is False
    assert second.state.revision == 1


def test_acknowledged_event_is_not_pending(repository, binding, fetch_approved):
    acknowledge_story_event_atomic(
        repository, "delivery-session", binding, fetch_approved
    )

    assert (
        get_pending_story_event(repository, "delivery-session", binding, fetch_approved)
        is None
    )


def test_missing_evidence_blocks_ack(repository, binding, fetch_approved):
    state = repository.load_state("delivery-session")

    updated = GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            "evidence": {},
            "revision": state.revision + 1,
        }
    )

    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    with pytest.raises(PermissionError):
        acknowledge_story_event_atomic(
            repository, "delivery-session", binding, fetch_approved
        )

    assert repository.load_state("delivery-session").acknowledged_story_events == []


def test_unqueued_event_cannot_be_acknowledged(repository, fetch_approved):
    binding = StoryEventBinding(
        source_story_id="STORY_019",
        event_key="EVT-CH01-901",
        chapter="CH01",
    )

    with pytest.raises(PermissionError):
        acknowledge_story_event_atomic(
            repository, "delivery-session", binding, fetch_approved
        )


def test_unqueued_ack_in_game_state_is_rejected(repository):
    state = repository.load_state("delivery-session")
    data = state.model_dump(mode="python")
    data["acknowledged_story_events"] = ["STORY_029"]

    with pytest.raises(ValueError):
        GameState.model_validate(data)


def test_duplicate_ack_in_game_state_is_rejected(repository):
    state = repository.load_state("delivery-session")
    data = state.model_dump(mode="python")
    data["acknowledged_story_events"] = ["STORY_020", "STORY_020"]

    with pytest.raises(ValueError):
        GameState.model_validate(data)


def test_legacy_save_defaults_to_no_ack(repository):
    state = repository.load_state("delivery-session")
    data = state.model_dump(mode="python")
    data.pop("acknowledged_story_events")

    restored = GameState.model_validate(data)
    assert restored.acknowledged_story_events == []


def test_concurrent_duplicate_ack_is_idempotent(
    repository, binding, fetch_approved, monkeypatch
):
    original_commit = repository.commit_state

    def simulated_race(*, expected_state, updated_state):
        original_commit(
            expected_state=expected_state,
            updated_state=updated_state,
        )
        raise ValueError("Simulated stale revision")

    monkeypatch.setattr(
        repository,
        "commit_state",
        simulated_race,
    )

    result = acknowledge_story_event_atomic(
        repository,
        "delivery-session",
        binding,
        fetch_approved,
    )

    assert result.created is False
    assert result.state.revision == 1


def test_unrelated_revision_conflict_is_not_ignored(
    repository, binding, fetch_approved, monkeypatch
):
    original_commit = repository.commit_state

    def unrelated_commit(*, expected_state, updated_state):
        unrelated = GameState.model_validate(
            {
                **expected_state.model_dump(mode="python"),
                "flags": ["TEST_OTHER_ACTION"],
                "revision": expected_state.revision + 1,
            }
        )

        original_commit(
            expected_state=expected_state,
            updated_state=unrelated,
        )
        raise ValueError("Unrelated revision conflict")

    monkeypatch.setattr(
        repository,
        "commit_state",
        unrelated_commit,
    )

    with pytest.raises(ValueError):
        acknowledge_story_event_atomic(
            repository,
            "delivery-session",
            binding,
            fetch_approved,
        )
