from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from crimescene.scenario.npc_knowledge import (
    DisclosureCondition,
    KnowledgeType,
    NPCKnowledgeCard,
)


class NPCDisclosureContext(BaseModel):
    """NPC 정보 접근 검사에 필요한 게임 상태."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    npc_id: str = Field(min_length=1)

    matched_question_ids: frozenset[str] = Field(default_factory=frozenset)

    collected_evidence_ids: frozenset[str] = Field(default_factory=frozenset)

    presented_evidence_ids: frozenset[str] = Field(default_factory=frozenset)

    unlocked_flag_ids: frozenset[str] = Field(default_factory=frozenset)


class AllowedKnowledge(BaseModel):
    """접근 검사를 통과한 NPC 지식."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_id: str
    knowledge_type: KnowledgeType
    content: str


def can_disclose_knowledge(
    card: NPCKnowledgeCard,
    context: NPCDisclosureContext,
) -> bool:
    """NPC와 게임 상태를 기준으로 지식 공개 가능 여부를 검사."""

    # 다른 NPC의 지식에는 접근할 수 없다.
    if card.npc_id != context.npc_id:
        return False

    rule = card.disclosure_rule
    condition = rule.condition
    reference_id = rule.reference_id

    # 처음부터 공개할 수 있는 정보
    if condition == DisclosureCondition.OPEN:
        return True

    # 조건부 정보에는 참조 ID가 필요하다.
    if reference_id is None:
        return False

    # 특정 질문 조건을 만족한 경우
    if condition == DisclosureCondition.QUESTION:
        return reference_id in context.matched_question_ids

    # 특정 증거를 획득한 경우
    if condition == DisclosureCondition.EVIDENCE_COLLECTED:
        return reference_id in context.collected_evidence_ids

    # 증거를 획득하고 NPC에게 직접 제시한 경우
    if condition == DisclosureCondition.EVIDENCE_PRESENTED:
        return (
            reference_id in context.collected_evidence_ids
            and reference_id in context.presented_evidence_ids
        )

    # 특정 이벤트가 해금된 경우
    if condition == DisclosureCondition.FLAG_UNLOCKED:
        return reference_id in context.unlocked_flag_ids

    # 정의되지 않은 조건은 기본적으로 차단한다.
    return False


def select_disclosable_knowledge(
    cards: Iterable[NPCKnowledgeCard],
    context: NPCDisclosureContext,
) -> list[AllowedKnowledge]:
    """접근이 허용된 지식만 선별한다."""

    allowed_cards = []

    for card in cards:
        if not can_disclose_knowledge(card, context):
            continue

        allowed_cards.append(
            AllowedKnowledge(
                knowledge_id=card.knowledge_id,
                knowledge_type=card.knowledge_type,
                content=card.content,
            )
        )

    return allowed_cards
