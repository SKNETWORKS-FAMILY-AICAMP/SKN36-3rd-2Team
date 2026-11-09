"""Issue #29 - 범인 지목 및 사건 결과 판정."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.evidence_collection import get_collection_progress
from crimescene.scenario.game_progress import (
    meets_accusation_requirements,
    transition_phase,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase, GameState

TOTAL_EVIDENCE = 10
TOTAL_SCORE = 21


class AccusationStatus(StrEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"


@dataclass(frozen=True, slots=True)
class AccusationResult:
    state: GameState
    status: AccusationStatus
    attempts_left: int


def can_accuse(
    state: GameState,
    evidence_rules: Mapping[str, EvidenceRule],
) -> bool:
    """증거 수집률 50% 및 11점 이상 조건을 검증합니다."""

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    progress = get_collection_progress(state, evidence_rules)

    if progress.total_count != TOTAL_EVIDENCE or progress.total != TOTAL_SCORE:
        raise ValueError("CASE-001 증거 규칙이 올바르지 않습니다.")

    if state.score != progress.score:
        raise ValueError("증거 점수의 무결성이 일치하지 않습니다.")

    return (
        state.phase in (GamePhase.INVESTIGATION, GamePhase.ACCUSATION)
        and state.outcome in (None, "ONGOING")
        and meets_accusation_requirements(state)
        and progress.collected_count * 2 >= progress.total_count
        and state.attempts_left > 0
    )


def enter_accusation(
    state: GameState,
    evidence_rules: Mapping[str, EvidenceRule],
) -> GameState:
    """지목 조건을 만족한 플레이어를 지목 단계로 전환합니다."""

    if state.phase not in (
        GamePhase.INVESTIGATION,
        GamePhase.ACCUSATION,
    ):
        raise PermissionError("현재 범인을 지목할 수 없습니다.")

    if state.outcome not in (None, "ONGOING"):
        raise PermissionError("이미 종료된 사건입니다.")

    if not can_accuse(state, evidence_rules):
        raise PermissionError("증거 수집률 50% 이상 및 11점 이상이 필요합니다.")

    if state.phase == GamePhase.ACCUSATION:
        return state

    return transition_phase(state, GamePhase.ACCUSATION)


def submit_accusation(
    *,
    state: GameState,
    suspect_id: str,
    truth: CaseTruth,
    evidence_rules: Mapping[str, EvidenceRule],
) -> AccusationResult:
    """서버 전용 사건 원장과 비교해 범인 지목을 판정합니다."""

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(suspect_id, str):
        raise TypeError("범인 지목 ID는 문자열이어야 합니다.")

    if suspect_id not in EXPECTED_CHARACTER_IDS:
        raise ValueError("등록되지 않은 NPC입니다.")

    if not isinstance(truth, CaseTruth):
        raise TypeError("서버 전용 사건 진실 원장이 필요합니다.")

    if (
        state.case_id != "CASE-001"
        or truth.case_id != state.case_id
        or truth.access_scope != "ENGINE_ONLY"
    ):
        raise ValueError("사건 진실 원장과 게임 상태가 일치하지 않습니다.")

    if truth.perpetrator_character_id not in EXPECTED_CHARACTER_IDS:
        raise ValueError("사건 진실 원장의 범인 ID가 올바르지 않습니다.")

    if state.phase == GamePhase.FINISHED:
        raise PermissionError("이미 종료된 사건입니다.")

    if not can_accuse(state, evidence_rules):
        return AccusationResult(
            state=state,
            status=AccusationStatus.NOT_ENOUGH_EVIDENCE,
            attempts_left=state.attempts_left,
        )

    if state.phase != GamePhase.ACCUSATION:
        raise PermissionError("지목 단계가 아닙니다.")

    # 클라이언트가 미해금 인물을 직접 지정하는 것을 서버에서 차단합니다.
    if suspect_id not in state.unlocked_characters:
        raise PermissionError("아직 해금되지 않은 NPC는 지목할 수 없습니다.")

    # 유효한 지목 시도에 대해서만 기회를 차감합니다.
    remaining = state.attempts_left - 1
    correct = suspect_id == truth.perpetrator_character_id

    if correct:
        outcome = "SUCCESS"
        phase = GamePhase.FINISHED
        status = AccusationStatus.CORRECT

    elif remaining == 0:
        outcome = "FAILURE"
        phase = GamePhase.FINISHED
        status = AccusationStatus.INCORRECT

    else:
        outcome = state.outcome
        phase = GamePhase.ACCUSATION
        status = AccusationStatus.INCORRECT

    updated = GameState.model_validate(
        {
            **state.model_dump(),
            "attempts_left": remaining,
            "outcome": outcome,
            "phase": phase,
            "revision": state.revision + 1,
        }
    )

    return AccusationResult(
        state=updated,
        status=status,
        attempts_left=remaining,
    )
