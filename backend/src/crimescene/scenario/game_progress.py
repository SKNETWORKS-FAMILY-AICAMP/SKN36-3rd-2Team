"""Issue #27 - 게임 초기화 및 진행 단계 관리."""

from collections.abc import Mapping

from crimescene.scenario.evidence_collection import get_collection_progress
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    ContentVersion,
    GamePhase,
    GameState,
)

CASE_ID = "CASE-001"
INITIAL_NPC = "C01"
ACCUSE_THRESHOLD = 11

ALLOWED_TRANSITIONS = {
    GamePhase.PROLOGUE: {GamePhase.INVESTIGATION},
    GamePhase.INVESTIGATION: {GamePhase.ACCUSATION},
    GamePhase.ACCUSATION: {
        GamePhase.INVESTIGATION,
        GamePhase.FINISHED,
    },
    GamePhase.FINISHED: set(),
}

EXPECTED_EVIDENCE_IDS = frozenset(f"E{i:02d}" for i in range(1, 11))
VALID_EVIDENCE_STAGES = frozenset({"found", "resolved"})
MIN_EVIDENCE_COUNT = 5

EXPANDED_EVIDENCE_IDS = frozenset(
    f"E{i:02d}" for i in range(1, 31)
)


def _legacy_accusation_requirements(state: GameState) -> bool:
    """CASE-001 범인 지목 최소 조건을 검증합니다."""

    collected_count = sum(
        evidence_id in EXPECTED_EVIDENCE_IDS
        and evidence_state.stage in VALID_EVIDENCE_STAGES
        for evidence_id, evidence_state in state.evidence.items()
    )

    return collected_count >= MIN_EVIDENCE_COUNT and state.score >= ACCUSE_THRESHOLD


def meets_accusation_requirements(
    state: GameState,
    evidence_rules: Mapping[str, EvidenceRule] | None = None,
) -> bool:
    """Evaluate accusation requirements from a trusted catalog."""

    # Preserve existing callers without a loaded catalog.
    if evidence_rules is None:
        return _legacy_accusation_requirements(state)

    ids = frozenset(evidence_rules)

    if ids not in {
        EXPECTED_EVIDENCE_IDS,
        EXPANDED_EVIDENCE_IDS,
    }:
        raise ValueError("Invalid evidence catalog")

    progress = get_collection_progress(state, evidence_rules)

    if state.score != progress.score:
        raise ValueError("Evidence score integrity mismatch")

    if ids == EXPECTED_EVIDENCE_IDS:
        if progress.total != 21:
            raise ValueError("Invalid legacy evidence score")

        return _legacy_accusation_requirements(state)

    if any(rule.score <= 0 for rule in evidence_rules.values()):
        raise ValueError("Expanded evidence scores must be positive")

    # Provisional policy: at least 50% of evidence and total score.
    return (
        progress.collected_count * 2 >= progress.total_count
        and progress.score * 2 >= progress.total
    )


def create_initial_state(
    session_id: str,
    *,
    content_version: ContentVersion = "case001_v7_1",
) -> GameState:
    """새 게임의 서버 관리 초기 상태를 생성합니다."""

    if not isinstance(session_id, str):
        raise TypeError("session_id는 문자열이어야 합니다.")

    if not session_id or session_id != session_id.strip() or len(session_id) > 128:
        raise ValueError("유효하지 않은 session_id입니다.")

    return GameState(
        case_id=CASE_ID,
        session_id=session_id,
        content_version=content_version,
        phase=GamePhase.PROLOGUE,
        unlocked_characters=[INITIAL_NPC],
        evidence={},
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome=None,
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


def transition_phase(
    state: GameState,
    target: GamePhase,
    *,
    evidence_rules: Mapping[str, EvidenceRule] | None = None,
) -> GameState:
    """진행 단계 전환을 검증하고 새로운 GameState를 반환합니다."""

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(target, GamePhase):
        raise TypeError("GamePhase가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건입니다.")

    if state.phase == target:
        return state

    if target not in ALLOWED_TRANSITIONS[state.phase]:
        raise ValueError(f"허용되지 않은 단계 전환: {state.phase} → {target}")

    # 지목 화면 진입 조건입니다.
    # 실제 지목 판정과 기회 차감은 #29에서 구현합니다.
    if target == GamePhase.ACCUSATION:
        if not meets_accusation_requirements(state, evidence_rules):
            raise PermissionError("증거 5개 이상 및 수집 점수 11점 이상이 필요합니다.")

        if state.attempts_left <= 0:
            raise PermissionError("남은 지목 기회가 없습니다.")
    # 사건 판정이 완료된 경우에만 종료할 수 있습니다.
    if target == GamePhase.FINISHED and state.outcome in (None, "ONGOING"):
        raise ValueError("사건 판정이 완료되지 않았습니다.")

    return GameState.model_validate(
        {
            **state.model_dump(),
            "phase": target,
            "revision": state.revision + 1,
        }
    )
