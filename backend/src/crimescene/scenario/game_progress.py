"""Issue #27 - 게임 초기화 및 진행 단계 관리."""

from crimescene.scenario.schemas.game_state import GamePhase, GameState

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


def create_initial_state(session_id: str) -> GameState:
    """새 게임의 서버 관리 초기 상태를 생성합니다."""

    if not isinstance(session_id, str):
        raise TypeError("session_id는 문자열이어야 합니다.")

    if not session_id or session_id != session_id.strip() or len(session_id) > 128:
        raise ValueError("유효하지 않은 session_id입니다.")

    return GameState(
        case_id=CASE_ID,
        session_id=session_id,
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
        if state.score < ACCUSE_THRESHOLD:
            raise PermissionError("증거 점수가 11점 이상이어야 합니다.")

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
