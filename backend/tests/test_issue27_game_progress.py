import pytest

from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.schemas.game_state import GamePhase, GameState


def test_initial_state():
    state = create_initial_state("test-session")

    assert state.case_id == "CASE-001"
    assert state.phase == GamePhase.PROLOGUE
    assert state.unlocked_characters == ["C01"]
    assert state.evidence == {}
    assert state.score == 0
    assert state.attempts_left == 3
    assert state.revision == 0


def test_prologue_to_investigation():
    state = create_initial_state("test-session")

    updated = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    assert updated.phase == GamePhase.INVESTIGATION
    assert updated.revision == 1
    assert state.phase == GamePhase.PROLOGUE


def test_invalid_phase_transition():
    state = create_initial_state("test-session")

    with pytest.raises(ValueError):
        transition_phase(state, GamePhase.FINISHED)


def test_accusation_requires_evidence():
    state = create_initial_state("test-session")
    state = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    with pytest.raises(PermissionError):
        transition_phase(state, GamePhase.ACCUSATION)


def test_accusation_allowed_after_threshold():
    state = create_initial_state("test-session")
    state = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    state = state.model_copy(update={"score": 11})

    updated = transition_phase(
        state,
        GamePhase.ACCUSATION,
    )

    assert updated.phase == GamePhase.ACCUSATION


def test_finished_requires_outcome():
    state = create_initial_state("test-session")
    state = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    state = state.model_copy(update={"score": 11})
    state = transition_phase(
        state,
        GamePhase.ACCUSATION,
    )

    with pytest.raises(ValueError):
        transition_phase(state, GamePhase.FINISHED)


def test_legacy_state_defaults_to_prologue():
    state = create_initial_state("test-session")

    old_data = state.model_dump()
    del old_data["phase"]

    restored = GameState.model_validate(old_data)

    assert restored.phase == GamePhase.PROLOGUE
