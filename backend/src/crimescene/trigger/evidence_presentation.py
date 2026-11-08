"""Issue #24 - 증거 제시 이벤트 및 NPC 트리거 연동.

보안 원칙:
- 실제 수집한 증거만 제시할 수 있다.
- 해금된 NPC에게만 제시할 수 있다.
- 서버가 허용한 NPC에게만 증거를 제시할 수 있다.
- 동일한 증거를 다시 제시해도 상태를 중복 변경하지 않는다.
- 공개 조건은 기존 PolicyEvaluator로 검증한다.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.npc_trigger import (
    NPCTriggerRule,
    apply_npc_triggers,
)


@dataclass(frozen=True, slots=True)
class EvidencePresentationResult:
    """증거 제시 결과."""

    state: GameState
    created: bool


@dataclass(frozen=True, slots=True)
class NPCDialogueEventResult:
    """증거 제시와 트리거 실행을 통합한 결과."""

    state: GameState
    presentation_created: bool
    trigger_ids: tuple[str, ...]
    matched_topics: tuple[str, ...]


def record_evidence_presentation(
    *,
    state: GameState,
    active_character_id: str,
    evidence_id: str,
    evidence_rules: Mapping[str, EvidenceRule],
    allowed_recipients: Mapping[str, frozenset[str]],
) -> EvidencePresentationResult:
    """증거 제시 조건을 검증한 뒤 GameState에 기록한다.

    allowed_recipients는 서버가 관리하는 증거별 허용 NPC 목록이다.
    플레이어 요청 데이터로부터 생성하면 안 된다.
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != "CASE-001":
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if not isinstance(active_character_id, str):
        raise TypeError("NPC ID는 문자열이어야 합니다.")

    if active_character_id not in EXPECTED_CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    if not isinstance(evidence_id, str):
        raise TypeError("증거 ID는 문자열이어야 합니다.")

    if not isinstance(evidence_rules, Mapping):
        raise TypeError("증거 규칙은 매핑이어야 합니다.")

    if not isinstance(allowed_recipients, Mapping):
        raise TypeError("허용 NPC 목록은 매핑이어야 합니다.")

    # 게임 종료 후에는 증거를 제시할 수 없다.
    if state.outcome not in (None, "ONGOING"):
        raise PermissionError("종료된 게임에서는 증거를 제시할 수 없습니다.")

    # 미해금 NPC 접근 차단
    if active_character_id not in state.unlocked_characters:
        raise PermissionError("아직 해금되지 않은 NPC입니다.")

    # 서버에 등록되지 않은 증거 차단
    rule = evidence_rules.get(evidence_id)

    if rule is None:
        raise ValueError("등록되지 않은 증거 ID입니다.")

    if not isinstance(rule, EvidenceRule):
        raise TypeError("증거 규칙 타입이 올바르지 않습니다.")

    # 실제 수집한 증거인지 확인
    evidence_state = state.evidence.get(evidence_id)

    if (
        evidence_state is None
        or evidence_state.stage not in PolicyEvaluator.VALID_EVIDENCE_STAGES
    ):
        raise PermissionError("수집하지 않은 증거입니다.")

    # 서버에서 정의한 증거별 제시 대상 확인
    recipients = allowed_recipients.get(evidence_id)

    if not isinstance(recipients, frozenset):
        raise PermissionError("증거 제시 허용 규칙이 없습니다.")

    if active_character_id not in recipients:
        raise PermissionError("해당 NPC에게 제시할 수 없는 증거입니다.")

    # GameState.presented는 NPC ID -> 증거 ID 목록 구조다.
    previous = state.presented.get(active_character_id, [])

    # 중복 제시는 아무 상태도 변경하지 않는다.
    if evidence_id in previous:
        return EvidencePresentationResult(
            state=state,
            created=False,
        )

    # 기존 GameState를 직접 수정하지 않는다.
    updated_presented = {
        npc_id: list(evidence_ids) for npc_id, evidence_ids in state.presented.items()
    }

    updated_presented.setdefault(
        active_character_id,
        [],
    ).append(evidence_id)

    # 전체 상태를 재검증하여 새로운 GameState 생성
    updated_state = GameState.model_validate(
        {
            **state.model_dump(),
            "presented": updated_presented,
            "revision": state.revision + 1,
        }
    )

    return EvidencePresentationResult(
        state=updated_state,
        created=True,
    )


def process_npc_dialogue_event(
    question: str,
    *,
    state: GameState,
    active_character_id: str,
    trigger_rules: Iterable[NPCTriggerRule],
    evaluator: PolicyEvaluator,
    evidence_rules: Mapping[str, EvidenceRule],
    allowed_recipients: Mapping[str, frozenset[str]],
    presented_evidence_id: str | None = None,
) -> NPCDialogueEventResult:
    """증거 제시와 대화 트리거를 순서대로 처리한다.

    처리 순서:
    1. 증거 제시 요청 검증
    2. 제시 기록을 임시 GameState에 반영
    3. 변경된 상태에서 트리거 접근 정책 재검증
    4. 최종 GameState 반환

    실제 영구 저장은 호출자가 수행해야 한다.
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    # 1. 증거 제시 요청이 없는 일반 대화
    if presented_evidence_id is None:
        presentation = EvidencePresentationResult(
            state=state,
            created=False,
        )

    # 2. 증거 제시 요청이 있는 대화
    else:
        presentation = record_evidence_presentation(
            state=state,
            active_character_id=active_character_id,
            evidence_id=presented_evidence_id,
            evidence_rules=evidence_rules,
            allowed_recipients=allowed_recipients,
        )

    # 3. 증거 제시 후의 상태를 기준으로 트리거 판정
    trigger_result = apply_npc_triggers(
        question,
        state=presentation.state,
        active_character_id=active_character_id,
        rules=trigger_rules,
        evaluator=evaluator,
    )

    # 4. 최종 결과 반환
    return NPCDialogueEventResult(
        state=trigger_result.state,
        presentation_created=presentation.created,
        trigger_ids=trigger_result.trigger_ids,
        matched_topics=trigger_result.matched_topics,
    )
