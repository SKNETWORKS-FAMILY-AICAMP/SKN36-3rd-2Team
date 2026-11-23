
"""Issue #134 - MCP용 NPC 지식 이중 접근 제어."""

from collections.abc import Mapping, Sequence
from typing import TypedDict

from crimescene.api.django_content_client import ApprovedNPCCards
from crimescene.scenario.npc_access import select_authorized_npc_cards
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GamePhase, GameState


class NPCCardPayload(TypedDict):
    card_id: str
    content: str
    truth_status: str


class NPCKnowledgePayload(TypedDict):
    character_id: str
    items: list[NPCCardPayload]


def select_mcp_npc_knowledge(
    *,
    state: GameState,
    active_character_id: str,
    trusted_cards: Sequence[Mapping[str, object]],
    evaluator: PolicyEvaluator,
    approved_cards: ApprovedNPCCards,
) -> NPCKnowledgePayload:
    """Django 승인과 GameState 접근 정책의 교집합만 반환합니다."""

    if state.phase != GamePhase.INVESTIGATION:
        raise PermissionError("조사 단계에서만 NPC 지식을 조회할 수 있습니다.")

    if state.outcome not in (None, "ONGOING"):
        raise PermissionError("종료된 게임에서는 조회할 수 없습니다.")

    if active_character_id not in state.unlocked_characters:
        raise PermissionError("해금되지 않은 NPC입니다.")

    if approved_cards.character_id != active_character_id:
        raise PermissionError("NPC 승인 응답이 일치하지 않습니다.")

    # Django에서 런타임 승인을 받은 KNOWLEDGE 카드만 사용합니다.
    approved = {
        card.card_id: card.content
        for card in approved_cards.cards
        if card.card_type == "KNOWLEDGE"
    }

    trusted_candidates = []

    for card in trusted_cards:
        card_id = card.get("id")

        if card_id not in approved:
            continue

        if (
            card.get("case_id") != state.case_id
            or card.get("character_id") != active_character_id
        ):
            continue

        # Django 응답과 서버의 신뢰 원본이 다르면 공개하지 않습니다.
        if card.get("body") != approved[card_id]:
            raise ValueError("NPC 지식 원본과 승인 콘텐츠가 일치하지 않습니다.")

        # 엔딩 조건이 있는 지식은 조사 단계에서 반환하지 않습니다.
        if card.get("required_ending") is not None:
            continue

        trusted_candidates.append(card)

    # 기존 NPC 정책 엔진의 증거·플래그·진술 단계 검증을 재사용합니다.
    authorized = select_authorized_npc_cards(
        trusted_candidates,
        state,
        evaluator,
        active_character_id=active_character_id,
    )

    return {
        "character_id": active_character_id,
        "items": [
            {
                "card_id": card.card_id,
                "content": card.content,
                "truth_status": card.truth_status,
            }
            for card in authorized[:5]
        ],
    }
