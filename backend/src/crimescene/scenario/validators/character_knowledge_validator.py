from collections.abc import Sequence

from crimescene.scenario.integrity import IntegrityViolation
from crimescene.scenario.schemas.character import (
    CharacterKnowledgeCard,
    CharacterProfile,
)


def find_circular_references(
    cards: dict[str, CharacterKnowledgeCard],
) -> set[str]:
    """지식 카드 간 순환 참조를 탐지한다."""

    states: dict[str, int] = {}
    cycles: set[str] = set()

    def visit(card_id: str) -> None:
        state = states.get(card_id, 0)

        # 현재 탐색 중인 카드를 다시 방문하면 순환 참조
        if state == 1:
            cycles.add(card_id)
            return

        # 이미 검사한 카드는 재검사하지 않는다.
        if state == 2:
            return

        states[card_id] = 1

        for previous_id in cards[card_id].supersedes:
            if previous_id in cards:
                visit(previous_id)

        states[card_id] = 2

    for card_id in cards:
        visit(card_id)

    return cycles


def validate_character_knowledge_progression(
    characters: Sequence[CharacterProfile],
) -> list[IntegrityViolation]:
    """NPC 지식 카드의 진술 대체 관계를 검증한다."""

    errors: list[IntegrityViolation] = []

    for character_index, character in enumerate(characters):
        cards = {card.id: card for card in character.cards}

        # 1. 존재하지 않는 이전 진술 참조 검사
        for card_index, card in enumerate(character.cards):
            for ref_index, previous_id in enumerate(card.supersedes):
                if previous_id not in cards:
                    errors.append(
                        IntegrityViolation(
                            path=(
                                f"characters[{character_index}]"
                                f".cards[{card_index}]"
                                f".supersedes[{ref_index}]"
                            ),
                            message=(f"존재하지 않는 이전 진술: {previous_id}"),
                        )
                    )

        # 2. 순환 참조 검사
        cycles = find_circular_references(cards)

        for card_id in sorted(cycles):
            errors.append(
                IntegrityViolation(
                    path=f"characters[{character_index}].cards",
                    message=(f"진술 대체 관계에 순환 참조가 있습니다: {card_id}"),
                )
            )

    return errors
