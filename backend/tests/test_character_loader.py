import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from crimescene.scenario.loaders.character_loader import (
    load_character_profiles,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_character(
    character_id="C01",
    card_id="K-C01-01",
):
    """테스트에 사용할 NPC 데이터."""

    return {
        "id": character_id,
        "name": "테스트 인물",
        "voice": "차분하고 신중한 말투",
        "appearance": "검은색 정장",
        "initial": "사건 당시 건물에 있었습니다.",
        "alibi": "20시까지 사무실에 있었습니다.",
        "secret_2026": "2026년의 비밀",
        "secret_2016": "2016년의 비밀",
        "trajectory": "사건이 진행될수록 태도가 변화한다.",
        "questions": [
            "사건 당시 어디에 있었습니까?",
        ],
        "cards": [
            {
                "id": card_id,
                "condition": "OPEN",
                "topic": "사건 당일",
                "body": "당시 사무실에 있었습니다.",
                "stance": "character_claim",
                "claim_group": "test_group",
                "stage_priority": 0,
                "supersedes": [],
                "effects": {
                    "find": [],
                    "flags": [],
                },
            }
        ],
    }


def write_characters(tmp_path, characters):
    """테스트 데이터를 임시 JSON 파일로 저장한다."""

    path = tmp_path / "characters.json"

    path.write_text(
        json.dumps(characters, ensure_ascii=False),
        encoding="utf-8",
    )

    return path


def test_load_valid_characters(tmp_path):
    """정상 NPC 데이터 로딩."""

    path = write_characters(
        tmp_path,
        [make_character()],
    )

    characters = load_character_profiles(path)

    assert len(characters) == 1
    assert characters[0].id == "C01"
    assert len(characters[0].cards) == 1


def test_duplicate_character_id(tmp_path):
    """NPC ID 중복 차단."""

    characters = [
        make_character("C01", "K-C01-01"),
        make_character("C01", "K-C01-02"),
    ]

    path = write_characters(tmp_path, characters)

    with pytest.raises(ValueError, match="중복된 NPC ID"):
        load_character_profiles(path)


def test_duplicate_knowledge_card_id(tmp_path):
    """지식 카드 ID 중복 차단."""

    characters = [
        make_character("C01", "K-TEST-01"),
        make_character("C02", "K-TEST-01"),
    ]

    path = write_characters(tmp_path, characters)

    with pytest.raises(ValueError, match="중복된 지식 카드 ID"):
        load_character_profiles(path)


def test_missing_required_field(tmp_path):
    """필수 프로필 정보 누락 차단."""

    character = make_character()

    del character["voice"]

    path = write_characters(
        tmp_path,
        [character],
    )

    with pytest.raises(ValidationError):
        load_character_profiles(path)


def test_invalid_character_id(tmp_path):
    """정의된 형식이 아닌 NPC ID 차단."""

    character = make_character(character_id="C11")

    path = write_characters(
        tmp_path,
        [character],
    )

    with pytest.raises(ValidationError):
        load_character_profiles(path)


def test_empty_character_list(tmp_path):
    """비어 있는 등장인물 목록 차단."""

    path = write_characters(tmp_path, [])

    with pytest.raises(ValueError, match="비어 있습니다"):
        load_character_profiles(path)


def test_real_v71_characters():
    """실제 v7.1 NPC 10명과 지식 카드 88개 검증."""

    root = PROJECT_ROOT / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/characters.json"))

    if not matches:
        pytest.skip("로컬 v7.1 원본 데이터가 없습니다.")

    assert len(matches) == 1

    characters = load_character_profiles(matches[0])

    assert len(characters) == 10

    character_ids = [character.id for character in characters]

    assert set(character_ids) == {f"C{i:02d}" for i in range(1, 11)}

    card_ids = [card.id for character in characters for card in character.cards]

    assert len(card_ids) == 88
    assert len(set(card_ids)) == 88
