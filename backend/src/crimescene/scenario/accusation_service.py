"""Issue #29 - 범인 지목 및 SQLite 원자적 저장."""

from collections.abc import Mapping
from dataclasses import replace

from crimescene.scenario.accusation import (
    AccusationResult,
    AccusationStatus,
    can_accuse,
    enter_accusation,
    submit_accusation,
)
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def enter_accusation_atomic(
    *,
    session_id: str,
    repository: SQLiteCase001Repository,
    evidence_rules: Mapping[str, EvidenceRule],
) -> GameState:
    """지목 가능 조건을 검증하고 진행 단계를 저장합니다."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("올바른 SQLite 저장소가 필요합니다.")

    # 서버에 저장된 최신 상태를 사용합니다.
    original = repository.load_state(session_id)

    updated = enter_accusation(
        original,
        evidence_rules,
    )

    # 이미 지목 단계라면 불필요한 revision 증가를 방지합니다.
    if updated is original:
        return original

    return repository.commit_state(
        expected_state=original,
        updated_state=updated,
    )


def submit_accusation_atomic(
    *,
    session_id: str,
    suspect_id: str,
    repository: SQLiteCase001Repository,
    truth: CaseTruth,
    evidence_rules: Mapping[str, EvidenceRule],
) -> AccusationResult:
    """범인 지목 결과와 남은 기회를 원자적으로 저장합니다."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("올바른 SQLite 저장소가 필요합니다.")

    # 클라이언트가 전달한 GameState는 사용하지 않습니다.
    original = repository.load_state(session_id)

    result = submit_accusation(
        state=original,
        suspect_id=suspect_id,
        truth=truth,
        evidence_rules=evidence_rules,
    )

    # 증거 부족 시 지목 기회를 차감하거나 DB를 변경하지 않습니다.
    if result.status == AccusationStatus.NOT_ENOUGH_EVIDENCE:
        return result

    # 정답·오답·남은 기회·종료 상태를 한 번에 저장합니다.
    committed = repository.commit_state(
        expected_state=original,
        updated_state=result.state,
    )

    return replace(
        result,
        state=committed,
        attempts_left=committed.attempts_left,
    )


def submit_accusation_request_atomic(
    *,
    session_id: str,
    suspect_id: str,
    expected_revision: int,
    repository: SQLiteCase001Repository,
    truth: CaseTruth,
    evidence_rules: Mapping[str, EvidenceRule],
) -> AccusationResult:
    """지목 단계 전환과 판정을 SQLite 트랜잭션 하나로 저장합니다."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("올바른 SQLite 저장소가 필요합니다.")

    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 0
    ):
        raise ValueError("올바르지 않은 revision입니다.")

    original = repository.load_state(session_id)

    # 동시 요청 및 이전 상태를 사용하는 중복 요청 차단
    if original.revision != expected_revision:
        raise ValueError("게임 상태가 변경되었습니다.")

    if original.phase not in (
        GamePhase.INVESTIGATION,
        GamePhase.ACCUSATION,
    ) or original.outcome not in (None, "ONGOING"):
        raise PermissionError("현재 범인을 지목할 수 없습니다.")

    # 증거 부족 시 상태와 지목 기회를 변경하지 않습니다.
    if not can_accuse(original, evidence_rules):
        return AccusationResult(
            state=original,
            status=AccusationStatus.NOT_ENOUGH_EVIDENCE,
            attempts_left=original.attempts_left,
        )

    # 단계 전환은 메모리에서만 수행합니다.
    # 중간 GameState를 DB에 저장하지 않습니다.
    accusation_state = enter_accusation(original, evidence_rules)

    result = submit_accusation(
        state=accusation_state,
        suspect_id=suspect_id,
        truth=truth,
        evidence_rules=evidence_rules,
    )

    # 오답이면서 기회가 남았다면 조사를 재개합니다.
    # 지목 판정과 단계 복귀를 하나의 SQLite 트랜잭션으로 저장합니다.
    next_phase = (
        GamePhase.INVESTIGATION
        if (result.status == AccusationStatus.INCORRECT and result.attempts_left > 0)
        else result.state.phase
    )

    updated = GameState.model_validate(
        {
            **result.state.model_dump(mode="python"),
            "phase": next_phase,
            "revision": original.revision + 1,
        }
    )

    # 원래 revision이 유지된 경우에만 원자적으로 저장됩니다.
    committed = repository.commit_state(
        expected_state=original,
        updated_state=updated,
    )

    return replace(
        result,
        state=committed,
        attempts_left=committed.attempts_left,
    )
