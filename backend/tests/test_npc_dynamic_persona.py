"""Issue #171 - dynamic persona security and context tests."""

from copy import deepcopy

import pytest

from crimescene.chat.npc_dynamic_persona import (
    CHAPTER_GUIDANCE,
    STAGE_GUIDANCE,
    build_dynamic_npc_persona,
    build_dynamic_npc_prompt,
)
from crimescene.chat.npc_persona import (
    NPCPersona,
    build_npc_system_prompt,
)
from crimescene.chat.npc_social_style import SOCIAL_STYLES
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)


NPC_IDS = [f"C{i:02d}" for i in range(1, 11)]


def make_state(**overrides):
    values = {
        "case_id": "CASE-001",
        "session_id": "persona-test-session",
        "content_version": "case001_1120",
        "phase": GamePhase.INVESTIGATION,
        "current_chapter": "CH01",
        "unlocked_chapters": ["CH00", "CH01"],
        "unlocked_characters": NPC_IDS.copy(),
        "npc_stages": {},
        "evidence": {},
        "flags": [],
        "presented": {},
        "attempts_left": 3,
        "score": 0,
        "outcome": None,
        "deep_eligible": False,
        "revision": 0,
        "disclosed_cards": [],
        "document_grants": [],
    }

    return GameState.model_validate({
        **values,
        **overrides,
    })


@pytest.mark.parametrize("character_id", NPC_IDS)
def test_each_npc_uses_existing_voice(character_id):
    state = make_state()

    result = build_dynamic_npc_persona(
        state=state,
        character_id=character_id,
    )

    assert result.character_id == character_id
    assert result.speaking_style == (
        SOCIAL_STYLES[character_id].speaking_style
    )

    assert result.stage == 1


@pytest.mark.parametrize(
    "chapter",
    ["CH00", "CH01", "CH02", "CH03", "CH04"],
)
def test_chapter_guidance(chapter):
    state = make_state(
        current_chapter=chapter,
        unlocked_chapters=[
            "CH00", "CH01", "CH02", "CH03", "CH04"
        ],
    )

    result = build_dynamic_npc_persona(
        state=state,
        character_id="C01",
    )

    assert result.chapter == chapter
    assert result.chapter_guidance == CHAPTER_GUIDANCE[chapter]


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_stage_guidance(stage):
    state = make_state(
        npc_stages={"C01": stage},
    )

    result = build_dynamic_npc_persona(
        state=state,
        character_id="C01",
    )

    assert result.stage == stage
    assert result.stage_guidance == STAGE_GUIDANCE[stage]


def test_ten_npc_styles_remain_distinct():
    state = make_state()

    styles = {
        build_dynamic_npc_persona(
            state=state,
            character_id=character_id,
        ).speaking_style
        for character_id in NPC_IDS
    }

    assert len(styles) == 10


def test_locked_character_denied():
    state = make_state(
        unlocked_characters=["C01"],
    )

    with pytest.raises(PermissionError):
        build_dynamic_npc_prompt(
            state=state,
            character_id="C02",
        )


def test_unknown_character_denied():
    with pytest.raises(ValueError):
        build_dynamic_npc_prompt(
            state=make_state(),
            character_id="C99",
        )


def test_legacy_dynamic_persona_denied():
    state = make_state(
        content_version="case001_v7_1",
    )

    with pytest.raises(ValueError):
        build_dynamic_npc_prompt(
            state=state,
            character_id="C01",
        )


def test_invalid_case_denied():
    state = make_state(case_id="CASE-999")

    with pytest.raises(ValueError):
        build_dynamic_npc_prompt(
            state=state,
            character_id="C01",
        )


def test_state_is_not_mutated():
    state = make_state(
        npc_stages={"C01": 2},
    )

    before = deepcopy(state.model_dump())

    build_dynamic_npc_prompt(
        state=state,
        character_id="C01",
    )

    assert state.model_dump() == before


def test_private_state_values_not_in_prompt():
    state = make_state(
        flags=["PRIVATE_FLAG_SENTINEL"],
        disclosed_cards=["PRIVATE_CARD_SENTINEL"],
        document_grants=["PRIVATE_DOCUMENT_SENTINEL"],
        npc_stages={"C01": 2, "C02": 3},
    )

    prompt = build_dynamic_npc_prompt(
        state=state,
        character_id="C01",
    )

    assert "PRIVATE_FLAG_SENTINEL" not in prompt
    assert "PRIVATE_CARD_SENTINEL" not in prompt
    assert "PRIVATE_DOCUMENT_SENTINEL" not in prompt
    assert "persona-test-session" not in prompt
    assert "현재 인물: C02" not in prompt
    assert "현재 대화 단계: 2" in prompt


def test_authorization_and_json_rules_remain_explicit():
    prompt = build_dynamic_npc_prompt(
        state=make_state(),
        character_id="C01",
    )

    assert "새로운 정보 공개 권한이 아니다" in prompt
    assert "정확한 원문 인용 규칙" in prompt
    assert "빈 인용 배열" in prompt
    assert "추가 JSON 필드" in prompt


@pytest.mark.parametrize(
    ("version", "title"),
    [
        ("case001_1120", "마지막 기록: 졸업하지 못한 밤"),
        ("case001_v7_1", "마지막 기록: 사라진 공동체"),
    ],
)
def test_version_aware_title(version, title):
    state = make_state(
        content_version=version,
    )

    personas = {
        "C01": NPCPersona(
            character_id="C01",
            name="Synthetic NPC",
            voice="정중체",
        ),
    }

    prompt = build_npc_system_prompt(
        personas,
        active_character_id="C01",
        state=state,
    )

    assert title in prompt
