import pytest

from crimescene.chat.npc_session import NPCSessionStore
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.schemas.game_state import GamePhase
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def setup_repository(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")

    state = create_initial_state("test-session")

    store = NPCSessionStore(repository=repository)
    store.select_npc(state, "C01")

    repository.register_state(state)

    return repository, state


def test_commit_state(tmp_path):
    repository, state = setup_repository(tmp_path)

    updated = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    committed = repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    restored = repository.load_state("test-session")
    selection = repository.load_selection("test-session")

    assert committed == updated
    assert restored.phase == GamePhase.INVESTIGATION
    assert restored.revision == 1
    assert selection == ("C01", 1)


def test_reject_stale_revision(tmp_path):
    repository, state = setup_repository(tmp_path)

    updated = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    with pytest.raises(ValueError):
        repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )

    assert repository.load_state(state.session_id) == updated


def test_reject_invalid_revision_increment(tmp_path):
    repository, state = setup_repository(tmp_path)

    updated = state.model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "revision": 5,
        }
    )

    with pytest.raises(ValueError):
        repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )

    assert repository.load_state(state.session_id) == state


def test_state_survives_repository_restart(tmp_path):
    db_path = tmp_path / "game.sqlite3"

    repository, state = setup_repository(tmp_path)

    updated = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    restarted = SQLiteCase001Repository(db_path)

    assert restarted.load_state(state.session_id) == updated
