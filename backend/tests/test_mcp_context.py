
"""Issue #134 - MCP 실행 컨텍스트 보안 테스트."""

import pytest

from crimescene.mcp.context import BoundMCPContext
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)


def make_state(session_id="mcp-session-a"):
    return transition_phase(
        create_initial_state(session_id),
        GamePhase.INVESTIGATION,
    )


def make_context(state):
    return BoundMCPContext.from_owned_game_state(
        state=state,
        load_state=lambda _: state,
    )


def test_valid_context_loads_state():
    state = make_state()
    scope = make_context(state)

    loaded = scope.load_verified_state()

    assert loaded == state
    assert loaded is not state


def test_loaded_state_cannot_mutate_original():
    state = make_state()
    scope = make_context(state)

    loaded = scope.load_verified_state()
    loaded.flags.append("TEST_FLAG")

    assert state.flags == []


def test_stale_revision_rejected():
    state = make_state()
    scope = make_context(state)

    state.revision += 1

    with pytest.raises(RuntimeError, match="상태가 변경"):
        scope.load_verified_state()


def test_cross_session_state_rejected():
    state_a = make_state("mcp-session-a")
    state_b = make_state("mcp-session-b")

    scope = BoundMCPContext.from_owned_game_state(
        state=state_a,
        load_state=lambda _: state_b,
    )

    with pytest.raises(PermissionError, match="세션"):
        scope.load_verified_state()


def test_case_tampering_rejected():
    state = make_state()
    scope = make_context(state)

    state.case_id = "CASE-999"

    with pytest.raises(PermissionError, match="사건"):
        scope.load_verified_state()


def test_invalid_evidence_stage_rejected():
    state = make_state()
    scope = make_context(state)

    state.evidence["E01"] = EvidenceState(stage="locked")

    with pytest.raises(PermissionError, match="증거 수집 상태"):
        scope.load_verified_state()


def test_locked_npc_rejected():
    state = make_state()

    with pytest.raises(ValueError, match="해금되지 않은 NPC"):
        BoundMCPContext.from_owned_game_state(
            state=state,
            load_state=lambda _: state,
            active_character_id="C02",
        )


def test_changed_npc_unlock_state_rejected():
    state = make_state()
    scope = make_context(state)

    state.unlocked_characters.append("C02")

    with pytest.raises(RuntimeError, match="상태가 변경"):
        scope.load_verified_state()
