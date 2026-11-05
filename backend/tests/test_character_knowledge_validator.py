from pathlib import Path

import pytest

from crimescene.scenario.loaders.character_loader import (
    load_character_profiles,
)
from crimescene.scenario.schemas.character import (
    CharacterProfile,
)
from crimescene.scenario.validators.character_knowledge_validator import (
    validate_character_knowledge_progression,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_card(
    card_id: str,
    supersedes: list[str] | None = None,
) -> dict:
    """테스트용 NPC 지식 카드를 생성한다."""

    return {
        "id": card_id,
        "condition": "OPEN",
        "topic": "사건 당일",
        "body": "사건에 대한 진술입니다.",
        "stance": "character_claim",
        "claim_group": "test_group",
        "stage_priority": 0,
        "supersedes": supersedes or [],
        "effects": {
            "find": [],
            "flags": [],
        },
    }


def make_character(
    character_id: str = "C01",
    cards: list[dict] | None = None,
) -> CharacterProfile:
    """테스트용 NPC 프로필을 생성한다."""

    if cards is None:
        cards = [make_card("K-C01-01")]

    return CharacterProfile.model_validate(
        {
            "id": character_id,
            "name": "테스트 인물",
            "voice": "차분한 말투",
            "appearance": "검은 정장",
            "initial": "사건에 대해 알고 있습니다.",
            "alibi": "당시 사무실에 있었습니다.",
            "secret_2026": "2026년 비밀",
            "secret_2016": "2016년 비밀",
            "trajectory": "사건이 진행되면서 태도가 변화한다.",
            "questions": ["사건 당시 어디에 있었습니까?"],
            "cards": cards,
        }
    )


def test_valid_knowledge_progression():
    """정상적인 진술 대체 관계는 오류가 없어야 한다."""

    character = make_character(
        cards=[
            make_card("K-C01-01"),
            make_card(
                "K-C01-02",
                supersedes=["K-C01-01"],
            ),
            make_card(
                "K-C01-03",
                supersedes=["K-C01-02"],
            ),
        ]
    )

    errors = validate_character_knowledge_progression([character])

    assert errors == []


def test_unknown_supersedes_reference():
    """존재하지 않는 이전 진술을 탐지한다."""

    character = make_character(
        cards=[
            make_card(
                "K-C01-01",
                supersedes=["K-UNKNOWN"],
            )
        ]
    )

    errors = validate_character_knowledge_progression([character])

    assert any("존재하지 않는 이전 진술" in error.message for error in errors)


def test_circular_knowledge_reference():
    """두 카드 간 순환 참조를 탐지한다."""

    character = make_character(
        cards=[
            make_card(
                "K-C01-01",
                supersedes=["K-C01-02"],
            ),
            make_card(
                "K-C01-02",
                supersedes=["K-C01-01"],
            ),
        ]
    )

    errors = validate_character_knowledge_progression([character])

    assert any("순환 참조" in error.message for error in errors)


def test_self_referencing_knowledge_card():
    """자기 자신을 대체하는 카드를 탐지한다."""

    character = make_character(
        cards=[
            make_card(
                "K-C01-01",
                supersedes=["K-C01-01"],
            )
        ]
    )

    errors = validate_character_knowledge_progression([character])

    assert any("순환 참조" in error.message for error in errors)


def test_cross_character_supersedes():
    """다른 NPC의 지식 카드를 대체하지 못하도록 검증한다."""

    character1 = make_character(
        character_id="C01",
        cards=[
            make_card(
                "K-C01-01",
                supersedes=["K-C02-01"],
            )
        ],
    )

    character2 = make_character(
        character_id="C02",
        cards=[make_card("K-C02-01")],
    )

    errors = validate_character_knowledge_progression([character1, character2])

    assert any(
        error.path.startswith("characters[0]")
        and "존재하지 않는 이전 진술" in error.message
        for error in errors
    )


def test_real_v71_knowledge_progression():
    """실제 v7.1 지식 카드 88개의 진술 관계를 검증한다."""

    root = PROJECT_ROOT / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/characters.json"))

    if not matches:
        pytest.skip("로컬 v7.1 데이터가 없습니다.")

    assert len(matches) == 1

    characters = load_character_profiles(matches[0])

    errors = validate_character_knowledge_progression(characters)

    card_count = sum(len(character.cards) for character in characters)

    reference_count = sum(
        len(card.supersedes) for character in characters for card in character.cards
    )

    assert len(characters) == 10
    assert card_count == 88
    assert reference_count == 29

    assert not errors, [f"{error.path}: {error.message}" for error in errors]
