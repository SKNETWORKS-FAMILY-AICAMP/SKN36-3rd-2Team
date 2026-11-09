"""Issue #29 - 범인 지목 및 사건 결과 테스트."""

import pytest

from crimescene.scenario.accusation import (
    AccusationStatus,
    can_accuse,
    enter_accusation,
    submit_accusation,
)
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GamePhase


def make_rules():
    scores = [1, 2, 3, 2, 3, 3, 2, 2, 1, 2]

    return {
        f"E{i:02d}": EvidenceRule(
            name=f"Test Evidence {i}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for i, score in enumerate(scores, start=1)
    }


def make_truth():
    # 실제 범인이 아닌 테스트 전용 정답입니다.
    return CaseTruth(
        case_id="CASE-001",
        perpetrator_character_id="C03",
        motive="test motive",
        cause_of_death="test cause",
        crime_method="test method",
        crime_event_id="EVT-TEST",
    )


def make_state(evidence_ids=("E01", "E02", "E03", "E04", "E05")):
    rules = make_rules()
    state = create_initial_state("issue29-test")

    return state.model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "evidence": {
                evidence_id: EvidenceState(stage="found")
                for evidence_id in evidence_ids
            },
            "score": sum(rules[evidence_id].score for evidence_id in evidence_ids),
        }
    )


def accuse(state, suspect="C02"):
    return submit_accusation(
        state=state,
        suspect_id=suspect,
        truth=make_truth(),
        evidence_rules=make_rules(),
    )


def test_can_accuse_with_five_evidence_and_11_points():
    state = make_state()

    assert can_accuse(state, make_rules()) is True


def test_cannot_accuse_below_50_percent():
    # 증거 4개, 점수 11점
    state = make_state(("E03", "E04", "E05", "E06"))

    assert can_accuse(state, make_rules()) is False


def test_cannot_accuse_below_11_points():
    # 증거 5개, 점수 8점
    state = make_state(("E01", "E02", "E04", "E09", "E10"))

    assert can_accuse(state, make_rules()) is False


def test_enter_accusation():
    state = make_state()

    updated = enter_accusation(state, make_rules())

    assert updated.phase == GamePhase.ACCUSATION
    assert updated.revision == state.revision + 1


def test_correct_accusation_ends_game():
    state = enter_accusation(make_state(), make_rules())

    result = accuse(state, suspect="C03")

    assert result.status == AccusationStatus.CORRECT
    assert result.state.phase == GamePhase.FINISHED
    assert result.state.outcome == "SUCCESS"
    assert result.attempts_left == 2


def test_wrong_accusation_consumes_one_attempt():
    state = enter_accusation(make_state(), make_rules())

    result = accuse(state)

    assert result.status == AccusationStatus.INCORRECT
    assert result.attempts_left == 2
    assert result.state.phase == GamePhase.ACCUSATION
    assert result.state.outcome is None


def test_three_wrong_attempts_end_game():
    state = enter_accusation(make_state(), make_rules())

    for _ in range(3):
        state = accuse(state).state

    assert state.attempts_left == 0
    assert state.phase == GamePhase.FINISHED
    assert state.outcome == "FAILURE"


def test_finished_game_rejects_accusation():
    state = enter_accusation(make_state(), make_rules())

    finished = accuse(state, suspect="C03").state

    with pytest.raises(PermissionError):
        accuse(finished)


def test_invalid_suspect_does_not_consume_attempt():
    state = enter_accusation(make_state(), make_rules())

    with pytest.raises(ValueError):
        accuse(state, suspect="C99")

    assert state.attempts_left == 3


def test_not_enough_evidence_does_not_consume_attempt():
    state = make_state(("E01",))

    result = accuse(state)

    assert result.status == AccusationStatus.NOT_ENOUGH_EVIDENCE
    assert result.attempts_left == 3
    assert result.state == state


def test_score_tampering_is_rejected():
    state = make_state().model_copy(update={"score": 20})

    with pytest.raises(ValueError):
        can_accuse(state, make_rules())
