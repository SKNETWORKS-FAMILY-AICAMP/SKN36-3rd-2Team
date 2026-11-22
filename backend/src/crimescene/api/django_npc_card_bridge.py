"""Django NPC 카드와 기존 v7.1 RAG 공개 정책을 연결합니다."""

from collections.abc import Iterable, Mapping

from crimescene.api.django_content_client import (
    ApprovedNPCCard,
    ApprovedNPCCards,
)
from crimescene.scenario.npc_access import select_authorized_npc_cards
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GameState


def select_disclosed_django_cards(
    *,
    django_cards: ApprovedNPCCards,
    state: GameState,
    evaluator: PolicyEvaluator,
    legacy_cards: Iterable[Mapping[str, object]],
    verified_mapping: Mapping[str, str],
    active_character_id: str,
) -> list[ApprovedNPCCard]:
    """승인·접근 정책·실제 공개 기록이 모두 일치하는 카드만 선택합니다."""

    if not isinstance(django_cards, ApprovedNPCCards):
        raise TypeError("올바른 Django NPC 카드 응답이 필요합니다.")

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(evaluator, PolicyEvaluator):
        raise TypeError("RAG 접근 정책 평가기가 필요합니다.")

    if not isinstance(verified_mapping, Mapping):
        raise TypeError("검증된 카드 ID 매핑이 필요합니다.")

    if django_cards.character_id != active_character_id:
        raise ValueError("조회한 NPC와 현재 NPC가 일치하지 않습니다.")

    # 매핑은 서버에서 검증한 값만 사용합니다.
    if any(
        not isinstance(source, str)
        or not isinstance(target, str)
        or not source
        or not target
        for source, target in verified_mapping.items()
    ):
        raise ValueError("카드 ID 매핑이 올바르지 않습니다.")

    if len(set(verified_mapping.values())) != len(verified_mapping):
        raise ValueError("서로 다른 카드가 동일한 RAG 카드에 연결되었습니다.")

    # 미해금 NPC는 카드 조회를 허용하지 않습니다.
    if active_character_id not in state.unlocked_characters:
        return []

    # 기존 RAG의 NPC·증거·플래그·진술 접근 정책을 재사용합니다.
    authorized = select_authorized_npc_cards(
        legacy_cards,
        state,
        evaluator,
        active_character_id=active_character_id,
    )

    authorized_by_id = {card.card_id: card for card in authorized}
    disclosed_ids = set(state.disclosed_cards)

    visible: list[ApprovedNPCCard] = []

    for django_card in django_cards.cards:
        legacy_id = verified_mapping.get(django_card.card_id)

        if legacy_id is None or legacy_id not in disclosed_ids:
            continue

        legacy_card = authorized_by_id.get(legacy_id)

        if legacy_card is None:
            continue

        # 동일 카드로 검증된 콘텐츠만 연결합니다.
        # ID만 같고 원문이 다르면 공개하지 않습니다.
        if django_card.content != legacy_card.content:
            continue

        visible.append(django_card)

    return visible
