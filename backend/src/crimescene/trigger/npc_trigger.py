"""Issue #24 - NPC 대화 트리거 엔진.

질문 키워드와 기존 접근 정책을 함께 검증한다.
트리거 규칙은 반드시 서버에서 관리한다.
"""

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GameState

MAX_QUERY_LENGTH = 4000


def _normalize(text: str) -> str:
    """유니코드, 대소문자, 공백을 정규화한다."""

    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class NPCTriggerRule(BaseModel):
    """서버에서 관리하는 NPC 트리거 정의.

    비밀 진술의 본문은 이 모델에 포함하지 않는다.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )

    trigger_id: str = Field(pattern=r"^TRG-[A-Z0-9_-]+$")

    character_id: str = Field(pattern=r"^C(0[1-9]|10)$")

    policy_id: str = Field(pattern=r"^POL-.+$")

    topic: str = Field(
        min_length=1,
        max_length=80,
    )

    phrases: tuple[str, ...] = Field(
        min_length=1,
        max_length=20,
    )

    grant_flags: tuple[str, ...] = ()

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("트리거 주제에 불필요한 공백이 있습니다.")

        return value

    @field_validator("phrases", "grant_flags")
    @classmethod
    def validate_items(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized: set[str] = set()

        for value in values:
            if not value.strip() or value != value.strip():
                raise ValueError("트리거 항목에 빈 문자열 또는 앞뒤 공백이 있습니다.")

            key = _normalize(value)

            if key in normalized:
                raise ValueError("트리거 항목이 중복됐습니다.")

            normalized.add(key)

        return values


@dataclass(frozen=True, slots=True)
class NPCTriggerResult:
    """검증을 통과한 트리거와 갱신된 게임 상태."""

    state: GameState

    trigger_ids: tuple[str, ...]

    matched_topics: tuple[str, ...]


def apply_npc_triggers(
    question: str,
    *,
    state: GameState,
    active_character_id: str,
    rules: Iterable[NPCTriggerRule],
    evaluator: PolicyEvaluator,
) -> NPCTriggerResult:
    """질문과 접근 정책을 검사한 뒤 게임 상태를 갱신한다.

    보안 처리:
        1. 입력값 검증
        2. NPC 해금 상태 확인
        3. 질문 키워드 검사
        4. 기존 PolicyEvaluator 검증
        5. 허용된 플래그만 추가
        6. GameState revision 증가

    실제 DB 저장은 호출자가 담당한다.
    """

    # ==================================================
    # 1. 입력 검증
    # ==================================================

    if not isinstance(question, str):
        raise TypeError("질문은 문자열이어야 합니다.")

    if not question.strip() or len(question) > MAX_QUERY_LENGTH:
        raise ValueError("질문이 비어 있거나 너무 깁니다.")

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != "CASE-001":
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if not isinstance(active_character_id, str):
        raise TypeError("NPC ID는 문자열이어야 합니다.")

    if not isinstance(evaluator, PolicyEvaluator):
        raise TypeError("PolicyEvaluator가 필요합니다.")

    if isinstance(rules, (str, bytes)):
        raise TypeError("트리거 규칙은 NPCTriggerRule 목록이어야 합니다.")

    rule_list = tuple(rules)

    seen_ids: set[str] = set()

    for rule in rule_list:
        if not isinstance(rule, NPCTriggerRule):
            raise TypeError("검증된 NPCTriggerRule만 사용할 수 있습니다.")

        if rule.trigger_id in seen_ids:
            raise ValueError("중복된 트리거 ID입니다.")

        seen_ids.add(rule.trigger_id)

    # ==================================================
    # 2. NPC 해금 상태 검사
    # ==================================================

    if active_character_id not in state.unlocked_characters:
        return NPCTriggerResult(
            state=state,
            trigger_ids=(),
            matched_topics=(),
        )

    # ==================================================
    # 3. 질문 정규화
    # ==================================================

    normalized_question = _normalize(question)

    trigger_ids: list[str] = []
    topics: list[str] = []
    new_flags: list[str] = []

    existing_flags = set(state.flags)

    # ==================================================
    # 4. 트리거 감지 및 접근 정책 검증
    # ==================================================

    for rule in rule_list:
        # 다른 NPC의 트리거는 무시
        if rule.character_id != active_character_id:
            continue

        # 사전에 정의한 키워드 중 하나라도 일치해야 함
        matched = any(
            _normalize(phrase) in normalized_question for phrase in rule.phrases
        )

        if not matched:
            continue

        # 기존 GameState와 접근 정책으로 승인 여부 판단
        allowed = evaluator.is_allowed(
            rule.policy_id,
            state,
            active_character_id=active_character_id,
            matched_topics=(rule.topic,),
        )

        if not allowed:
            continue

        # ==================================================
        # 5. 승인된 트리거 기록
        # ==================================================

        trigger_ids.append(rule.trigger_id)

        if rule.topic not in topics:
            topics.append(rule.topic)

        # 서버가 정의한 플래그만 추가한다.
        for flag in rule.grant_flags:
            if flag not in existing_flags:
                new_flags.append(flag)
                existing_flags.add(flag)

    # ==================================================
    # 6. 게임 상태 갱신
    # ==================================================

    if not new_flags:
        updated_state = state

    else:
        # 기존 GameState 객체는 변경하지 않는다.
        updated_state = state.model_copy(
            update={
                "flags": [
                    *state.flags,
                    *new_flags,
                ],
                "revision": state.revision + 1,
            },
            deep=True,
        )

    return NPCTriggerResult(
        state=updated_state,
        trigger_ids=tuple(trigger_ids),
        matched_topics=tuple(topics),
    )
