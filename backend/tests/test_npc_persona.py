"""CASE-001 NPC 페르소나의 최소 정보 노출 및 접근 제어 테스트."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from crimescene.chat.npc_persona import (
    build_npc_system_prompt,
    load_npc_personas,
)
from crimescene.scenario.schemas.game_state import GameState


def _character(index: int) -> dict:
    character_id = f"C{index:02d}"
    return {
        "id": character_id,
        "name": f"테스트 인물 {index}",
        "voice": f"테스트 말투 {index}",
        "appearance": "비공개 외형 단서",
        "initial": "PRIVATE_INITIAL_TEST",
        "alibi": "PRIVATE_ALIBI_TEST",
        "secret_2026": "PRIVATE_SECRET_2026",
        "secret_2016": "PRIVATE_SECRET_2016",
        "trajectory": "PRIVATE_TRAJECTORY_TEST",
        "questions": ["PRIVATE_QUESTION_TEST"],
        "cards": [
            {
                "id": f"K-{character_id}-01",
                "condition": "OPEN",
                "topic": "테스트 질문",
                "body": "PRIVATE_KNOWLEDGE_TEST",
                "stance": "character_claim",
                "claim_group": "test",
                "stage_priority": 0,
                "supersedes": [],
                "effects": {"find": [], "flags": []},
            }
        ],
    }


def _write(tmp_path, profiles: list[dict]):
    path = tmp_path / "characters.json"
    path.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
    return path


def _state(*, unlocked=None, case_id="CASE-001") -> GameState:
    return GameState(
        case_id=case_id,
        session_id="TEST-SESSION",
        unlocked_characters=(
            [f"C{i:02d}" for i in range(1, 11)] if unlocked is None else unlocked
        ),
        evidence={},
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


@pytest.fixture
def personas(tmp_path):
    return load_npc_personas(_write(tmp_path, [_character(i) for i in range(1, 11)]))


def test_loads_exactly_ten_personas(personas):
    assert set(personas) == {f"C{i:02d}" for i in range(1, 11)}
    assert personas["C01"].name == "테스트 인물 1"
    assert personas["C10"].voice == "테스트 말투 10"


def test_persona_is_minimal_and_does_not_export_secrets(personas):
    persona = personas["C01"]
    assert set(persona.__dataclass_fields__) == {"character_id", "name", "voice"}
    prompt = build_npc_system_prompt(
        personas, active_character_id="C01", state=_state()
    )
    assert "테스트 말투 1" in prompt
    for secret in (
        "PRIVATE_INITIAL_TEST",
        "PRIVATE_ALIBI_TEST",
        "PRIVATE_SECRET_2026",
        "PRIVATE_SECRET_2016",
        "PRIVATE_TRAJECTORY_TEST",
        "PRIVATE_QUESTION_TEST",
        "PRIVATE_KNOWLEDGE_TEST",
        "비공개 외형 단서",
    ):
        assert secret not in prompt


def test_different_npcs_have_distinct_prompts(personas):
    prompts = {
        character_id: build_npc_system_prompt(
            personas, active_character_id=character_id, state=_state()
        )
        for character_id in personas
    }
    assert len(set(prompts.values())) == 10
    assert "테스트 말투 2" not in prompts["C01"]
    assert "테스트 말투 1" not in prompts["C02"]


def test_intentional_claim_distinguished_from_fact(personas):
    prompt = build_npc_system_prompt(
        personas, active_character_id="C01", state=_state()
    )
    assert "character_claim" in prompt
    assert "검증된 사실이 아닙니다" in prompt
    assert "거짓말" in prompt


def test_locked_npc_rejected(personas):
    with pytest.raises(PermissionError, match="잠긴 NPC"):
        build_npc_system_prompt(
            personas, active_character_id="C02", state=_state(unlocked=["C01"])
        )


def test_unknown_npc_id_rejected(personas):
    with pytest.raises(ValueError, match="유효하지 않은 NPC ID"):
        build_npc_system_prompt(personas, active_character_id="C11", state=_state())


def test_unregistered_npc_rejected(personas):
    with pytest.raises(ValueError, match="등록되지 않은 NPC"):
        build_npc_system_prompt(
            {"C02": personas["C02"]}, active_character_id="C01", state=_state()
        )


def test_mismatched_persona_rejected(personas):
    with pytest.raises(ValueError, match="일치하지 않습니다"):
        build_npc_system_prompt(
            {"C01": personas["C02"]}, active_character_id="C01", state=_state()
        )


def test_invalid_case_id_rejected(personas):
    with pytest.raises(ValueError, match="사건 ID"):
        build_npc_system_prompt(
            personas, active_character_id="C01", state=_state(case_id="OTHER")
        )


def test_missing_one_character_rejected(tmp_path):
    with pytest.raises(ValueError, match="총 10명"):
        load_npc_personas(_write(tmp_path, [_character(i) for i in range(1, 10)]))


def test_duplicate_npc_rejected(tmp_path):
    profiles = [_character(i) for i in range(1, 11)]
    profiles[9]["id"] = "C01"
    with pytest.raises(ValueError, match="중복된 NPC ID"):
        load_npc_personas(_write(tmp_path, profiles))


def test_malformed_persona_data_rejected(tmp_path):
    profiles = [_character(i) for i in range(1, 11)]
    del profiles[0]["voice"]
    with pytest.raises(ValidationError):
        load_npc_personas(_write(tmp_path, profiles))


def test_blank_voice_is_rejected(tmp_path):
    profiles = [_character(i) for i in range(1, 11)]
    profiles[0]["voice"] = "   "
    with pytest.raises(ValueError, match="말투가 비어"):
        load_npc_personas(_write(tmp_path, profiles))


def test_real_case001_persona_loading():
    """로컬 관리자 원본이 있을 때 실제 NPC 10명의 페르소나를 검증한다."""
    root = Path(__file__).resolve().parents[2] / ".local" / "case001_v7_1"
    matches = list(root.glob("*/data/characters.json"))
    if not matches:
        pytest.skip("로컬 관리자 전용 CASE-001 데이터가 없습니다.")
    assert len(matches) == 1
    personas = load_npc_personas(matches[0])
    assert len(personas) == 10
    for npc_id in sorted(personas):
        persona = personas[npc_id]
        prompt = build_npc_system_prompt(
            personas, active_character_id=npc_id, state=_state()
        )
        assert persona.name in prompt
        assert persona.voice in prompt
        assert "secret_2016" not in prompt
        assert "secret_2026" not in prompt
