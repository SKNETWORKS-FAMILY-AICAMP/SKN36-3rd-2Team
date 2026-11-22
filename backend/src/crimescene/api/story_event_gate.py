"""플레이어 진행 상태에 따른 스토리 이벤트 공개 검증."""

from crimescene.api.django_content_client import ApprovedStoryEvent
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)

COLLECTED_STAGES = frozenset({"found", "resolved"})


def select_releasable_story_event(
    event: ApprovedStoryEvent,
    state: GameState,
) -> ApprovedStoryEvent | None:
    """필수 증거 및 현재 해금 범위를 충족한 이벤트만 선택합니다."""

    if not isinstance(event, ApprovedStoryEvent):
        raise TypeError("승인된 스토리 이벤트가 필요합니다.")

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != "CASE-001":
        return None

    if state.phase == GamePhase.PROLOGUE:
        return None

    # 아직 챕터별 해금 상태가 없으므로 CH01~CH04는 차단합니다.
    # 해금되지 않은 챕터의 스토리는 차단합니다.
    if event.chapter not in state.unlocked_chapters:
        return None

    # 현재 플레이 중인 챕터의 이벤트만 공개합니다.
    if event.chapter != state.current_chapter:
        return None

    collected = {
        evidence_id
        for evidence_id, evidence_state in state.evidence.items()
        if evidence_state.stage in COLLECTED_STAGES
    }

    if not set(event.required_evidence_ids).issubset(collected):
        return None

    return event
