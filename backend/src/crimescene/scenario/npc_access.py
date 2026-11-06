from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GameState


class NPCKnowledgeCardV71(AccessPolicy):
    """v7.1 NPC 지식 카드의 접근 제어 및 진술 진행 필드."""

    model_config = ConfigDict(
        extra="ignore",
        strict=True,
    )

    id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    character_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    body: str = Field(min_length=1)

    access_scope: Literal["character_only"]

    truth_status: Literal[
        "character_claim",
        "known_to_character",
    ]

    # 이전 진술을 대체하는 관계
    supersedes: list[str]

    # 진술 출력 우선순위
    stage_priority: int = Field(ge=0)


class AuthorizedNPCCard(BaseModel):
    """접근 검사를 통과한 NPC 지식."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    card_id: str
    character_id: str
    content: str

    truth_status: Literal[
        "character_claim",
        "known_to_character",
    ]


def select_authorized_npc_cards(
    cards: Iterable[Mapping[str, object]],
    state: GameState,
    evaluator: PolicyEvaluator,
    *,
    active_character_id: str,
    matched_topics: Iterable[str] = (),
) -> list[AuthorizedNPCCard]:
    """접근 권한과 진술 대체 관계를 적용해 NPC 지식을 반환한다."""

    # 1. 미해금 NPC 차단
    if active_character_id not in state.unlocked_characters:
        return []

    topics = tuple(matched_topics)

    eligible: list[tuple[AuthorizedNPCCard, NPCKnowledgeCardV71]] = []

    seen_ids: set[str] = set()

    for raw_card in cards:
        # 2. 데이터 구조 검증
        try:
            card = NPCKnowledgeCardV71.model_validate(raw_card)
        except ValidationError:
            continue

        # 3. 사건 및 NPC 확인
        if card.case_id != state.case_id:
            continue

        if card.character_id != active_character_id:
            continue

        if card.id in seen_ids:
            continue

        seen_ids.add(card.id)

        # 4. 등록된 접근 정책 확인
        if not evaluator.is_allowed(
            card.policy_id,
            state,
            active_character_id=active_character_id,
            matched_topics=topics,
        ):
            continue

        # 5. 카드 자체의 접근 조건도 확인
        card_policy = AccessPolicy(
            required_evidence=card.required_evidence,
            required_presentations=card.required_presentations,
            required_flags=card.required_flags,
            required_ending=card.required_ending,
            required_topics=card.required_topics,
            required_disclosed_cards=card.required_disclosed_cards,
            required_character=card.character_id,
        )

        card_evaluator = PolicyEvaluator({card.policy_id: card_policy})

        if not card_evaluator.is_allowed(
            card.policy_id,
            state,
            active_character_id=active_character_id,
            matched_topics=topics,
        ):
            continue

        # 6. 공개 가능한 진술만 후보로 등록
        authorized = AuthorizedNPCCard(
            card_id=card.id,
            character_id=card.character_id,
            content=card.body,
            truth_status=card.truth_status,
        )

        eligible.append((authorized, card))

    # 7. 현재 공개 가능한 진술이 대체하는 이전 진술 ID
    superseded_ids: set[str] = set()

    for _, card in eligible:
        superseded_ids.update(card.supersedes)

    # 8. 대체된 이전 진술 제외
    visible = [
        (authorized, card)
        for authorized, card in eligible
        if authorized.card_id not in superseded_ids
    ]

    # 9. 우선순위가 높은 진술부터 정렬
    # 같은 우선순위에서는 기존 입력 순서를 유지한다.
    visible.sort(
        key=lambda item: item[1].stage_priority,
        reverse=True,
    )

    # 10. 내부 메타데이터 없이 공개용 정보만 반환
    return [authorized for authorized, _ in visible]
