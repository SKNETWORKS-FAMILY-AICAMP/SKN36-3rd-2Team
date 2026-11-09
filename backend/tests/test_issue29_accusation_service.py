"""Issue #29 - 범인 지목 SQLite 통합 테스트."""

import sqlite3

import pytest

from crimescene.scenario.accusation import AccusationStatus, can_accuse
from crimescene.scenario.accusation_service import (
    enter_accusation_atomic,
    submit_accusation_atomic,
)
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


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
    # 실제 사건의 정답이 아닌 테스트용 범인입니다.
    return CaseTruth(
        case_id="CASE-001",
        perpetrator_character_id="C03",
        motive="test motive",
        cause_of_death="test cause",
        crime_method="test method",
        crime_event_id="EVT-TEST",
    )


@pytest.fixture
def game(tmp_path):
    path = tmp_path / "issue29.sqlite3"
    repository = SQLiteCase001Repository(path)

    state = create_initial_state("issue29-service").model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "evidence": {
                evidence_id: EvidenceState(stage="found")
                for evidence_id in ("E01", "E02", "E03", "E04", "E05")
            },
            "score": 11,
        }
    )

    repository.save_selection(
        state.session_id,
        "C01",
        state.revision,
    )
    repository.register_state(state)

    return repository, state, path


def enter(repository, state):
    return enter_accusation_atomic(
        session_id=state.session_id,
        repository=repository,
        evidence_rules=make_rules(),
    )


def accuse(repository, state, suspect="C02"):
    return submit_accusation_atomic(
        session_id=state.session_id,
        suspect_id=suspect,
        repository=repository,
        truth=make_truth(),
        evidence_rules=make_rules(),
    )


def test_enter_accusation_is_persisted(game):
    repository, state, _ = game

    updated = enter(repository, state)

    assert updated.phase == GamePhase.ACCUSATION
    assert updated.revision == 1
    assert repository.load_state(state.session_id) == updated


def test_enter_accusation_is_idempotent(game):
    repository, state, _ = game

    first = enter(repository, state)
    second = enter(repository, state)

    assert second == first
    assert second.revision == 1


def test_correct_accusation_is_persisted(game):
    repository, state, _ = game

    enter(repository, state)

    result = accuse(repository, state, suspect="C03")

    saved = repository.load_state(state.session_id)

    assert result.status == AccusationStatus.CORRECT
    assert result.attempts_left == 2
    assert saved.outcome == "SUCCESS"
    assert saved.phase == GamePhase.FINISHED
    assert saved == result.state
    assert can_accuse(saved, make_rules()) is False

    assert repository.load_selection(state.session_id) == (
        "C01",
        saved.revision,
    )


def test_three_wrong_attempts_end_game(game):
    repository, state, _ = game

    enter(repository, state)

    for expected_attempts in (2, 1, 0):
        result = accuse(repository, state)

        assert result.status == AccusationStatus.INCORRECT
        assert result.attempts_left == expected_attempts

    saved = repository.load_state(state.session_id)

    assert saved.attempts_left == 0
    assert saved.outcome == "FAILURE"
    assert saved.phase == GamePhase.FINISHED
    assert saved.revision == 4


def test_finished_game_blocks_new_accusation(game):
    repository, state, _ = game

    enter(repository, state)
    accuse(repository, state, suspect="C03")

    before = repository.load_state(state.session_id)

    with pytest.raises(PermissionError):
        accuse(repository, state)

    after = repository.load_state(state.session_id)

    assert before == after


def test_failed_commit_rolls_back_verdict(game):
    repository, state, path = game

    enter(repository, state)

    before = repository.load_state(state.session_id)

    # 저장 실패 상황을 강제로 발생시킵니다.
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TRIGGER fail_verdict
            BEFORE UPDATE ON game_states
            BEGIN
                SELECT RAISE(ABORT, 'injected failure');
            END
            """
        )

    with pytest.raises(sqlite3.DatabaseError):
        accuse(repository, state, suspect="C03")

    after = repository.load_state(state.session_id)

    # 판정과 지목 기회 변경 모두 롤백돼야 합니다.
    assert after == before
    assert after.attempts_left == 3
    assert after.outcome is None
    assert repository.load_selection(state.session_id) == (
        "C01",
        before.revision,
    )
