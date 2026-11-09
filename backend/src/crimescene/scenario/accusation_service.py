"""Issue #29 - 범인 지목 및 SQLite 원자적 저장."""

from collections.abc import Mapping
from dataclasses import replace

from crimescene.scenario.accusation import (
    AccusationResult,
    AccusationStatus,
    enter_accusation,
    submit_accusation,
)
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
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
