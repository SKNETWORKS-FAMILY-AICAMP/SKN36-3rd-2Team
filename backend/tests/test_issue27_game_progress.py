import pytest

from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)


def with_sufficient_evidence(state: GameState) -> GameState:
    """지목 최소 조건인 증거 5개 및 11점을 충족하는 상태 생성."""

    return state.model_copy(
        update={
            "evidence": {
                evidence_id: EvidenceState(stage="found")
                for evidence_id in (
                    "E01",
                    "E02",
                    "E03",
                    "E04",
                    "E05",
                )
            },
            "score": 11,
        }
    )


def test_initial_state():
    """게임 초기 상태 검증."""

    state = create_initial_state("test-session")

    assert state.case_id == "CASE-001"
    assert state.phase == GamePhase.PROLOGUE
    assert state.unlocked_characters == ["C01"]
    assert state.evidence == {}
    assert state.score == 0
    assert state.attempts_left == 3
    assert state.revision == 0


def test_prologue_to_investigation():
    """프롤로그에서 조사 단계로 정상 전환."""

    state = create_initial_state("test-session")

    updated = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    assert updated.phase == GamePhase.INVESTIGATION
    assert updated.revision == state.revision + 1
    assert state.phase == GamePhase.PROLOGUE


def test_invalid_phase_transition():
    """허용되지 않은 단계 전환 차단."""

    state = create_initial_state("test-session")

    with pytest.raises(ValueError):
        transition_phase(
            state,
            GamePhase.FINISHED,
        )


def test_accusation_requires_evidence():
    """증거가 없는 상태에서는 범인을 지목할 수 없음."""

    state = create_initial_state("test-session")

    state = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    with pytest.raises(PermissionError):
        transition_phase(
            state,
            GamePhase.ACCUSATION,
        )


def test_accusation_allowed_after_threshold():
    """증거 5개 이상 및 11점 이상이면 지목 단계 진입 가능."""

    state = create_initial_state("test-session")

    state = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    state = with_sufficient_evidence(state)

    updated = transition_phase(
        state,
        GamePhase.ACCUSATION,
    )

    assert updated.phase == GamePhase.ACCUSATION
    assert updated.score == 11
    assert len(updated.evidence) == 5
    assert updated.revision == state.revision + 1


def test_finished_requires_outcome():
    """사건 판정 없이 게임을 종료할 수 없음."""

    state = create_initial_state("test-session")

    state = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    state = with_sufficient_evidence(state)

    state = transition_phase(
        state,
        GamePhase.ACCUSATION,
    )

    assert state.outcome is None

    with pytest.raises(ValueError):
        transition_phase(
            state,
            GamePhase.FINISHED,
        )


def test_legacy_state_defaults_to_prologue():
    """기존 GameState 데이터와의 하위 호환성 검증."""

    state = create_initial_state("test-session")

    old_data = state.model_dump()
    del old_data["phase"]

    restored = GameState.model_validate(old_data)

    assert restored.phase == GamePhase.PROLOGUE


def test_accusation_requires_five_evidence():
    """점수가 11점이어도 증거가 5개 미만이면 지목 차단."""

    state = create_initial_state("test-session")

    state = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    # 증거 4개, 점수 11점
    state = state.model_copy(
        update={
            "evidence": {
                evidence_id: EvidenceState(stage="found")
                for evidence_id in (
                    "E03",
                    "E04",
                    "E05",
                    "E06",
                )
            },
            "score": 11,
        }
    )

    assert len(state.evidence) == 4
    assert state.score == 11

    with pytest.raises(PermissionError):
        transition_phase(
            state,
            GamePhase.ACCUSATION,
        )


def test_accusation_requires_eleven_points():
    """증거가 5개여도 점수가 11점 미만이면 지목 차단."""

    state = create_initial_state("test-session")

    state = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    # 증거 5개, 점수 8점
    state = state.model_copy(
        update={
            "evidence": {
                evidence_id: EvidenceState(stage="found")
                for evidence_id in (
                    "E01",
                    "E02",
                    "E04",
                    "E09",
                    "E10",
                )
            },
            "score": 8,
        }
    )

    assert len(state.evidence) == 5
    assert state.score == 8

    with pytest.raises(PermissionError):
        transition_phase(
            state,
            GamePhase.ACCUSATION,
        )
