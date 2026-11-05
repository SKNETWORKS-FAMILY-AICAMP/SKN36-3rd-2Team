from collections import Counter
from pathlib import Path

from pydantic import TypeAdapter

from crimescene.scenario.schemas.character import CharacterProfile

_character_adapter = TypeAdapter(list[CharacterProfile])


def load_character_profiles(
    file_path: Path,
) -> list[CharacterProfile]:
    """v7.1 등장인물 프로필을 읽고 검증한다."""

    # 1. JSON 파일 읽기
    content = file_path.read_text(encoding="utf-8-sig")

    # 2. Pydantic 데이터 검증
    characters = _character_adapter.validate_json(content)

    if not characters:
        raise ValueError("등장인물 데이터가 비어 있습니다.")

    # 3. NPC ID 중복 검사
    character_ids = [character.id for character in characters]

    duplicate_characters = [
        character_id
        for character_id, count in Counter(character_ids).items()
        if count > 1
    ]

    if duplicate_characters:
        raise ValueError(f"중복된 NPC ID가 존재합니다: {duplicate_characters}")

    # 4. 지식 카드 ID 중복 검사
    card_ids = [card.id for character in characters for card in character.cards]

    duplicate_cards = [
        card_id for card_id, count in Counter(card_ids).items() if count > 1
    ]

    if duplicate_cards:
        raise ValueError(f"중복된 지식 카드 ID가 존재합니다: {duplicate_cards}")

    return characters
