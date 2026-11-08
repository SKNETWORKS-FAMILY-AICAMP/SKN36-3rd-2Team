"""Issue #22 - 실제 CASE-001 NPC 페르소나 통합 검증."""

from pathlib import Path

import pytest

from crimescene.chat.npc_behavior import build_npc_behavior_prompt
from crimescene.chat.npc_persona import (
    EXPECTED_CHARACTER_IDS,
    build_npc_system_prompt,
    load_npc_personas,
)
from crimescene.ingest.case001_dataset import load_npc_cards
from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.loaders.character_loader import (
    load_character_profiles,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GameState

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_ROOT = PROJECT_ROOT / ".local" / "case001_v7_1"


def find_source() -> Path:
    """기존 프로젝트의 v7.1 디렉터리 구조에서 원본을 찾는다."""

    matches = list(DATA_ROOT.glob("*/data/characters.json"))

    if not matches:
        pytest.skip("CASE-001 실제 데이터가 없습니다.")

    if len(matches) != 1:
        raise ValueError("CASE-001 원본 데이터 경로가 중복되었습니다.")

    data_dir = matches[0].parent

    required_files = (
        "characters.json",
        "npc_knowledge_cards.jsonl",
        "access_policies.json",
    )

    for filename in required_files:
        if not (data_dir / filename).is_file():
            raise FileNotFoundError(f"CASE-001 필수 파일이 없습니다: {filename}")

    return data_dir


@pytest.fixture(scope="module")
def case001():
    """실제 인물, 지식 카드, 접근 정책을 로딩한다."""

    data_dir = find_source()

    characters = load_character_profiles(data_dir / "characters.json")

    personas = load_npc_personas(data_dir / "characters.json")

    cards = load_npc_cards(data_dir / "npc_knowledge_cards.jsonl")

    policies = load_access_policies(data_dir / "access_policies.json")

    return {
        "characters": characters,
        "personas": personas,
        "cards": cards,
        "evaluator": PolicyEvaluator(policies),
    }


def make_state(
    *,
    unlocked_characters: list[str] | None = None,
) -> GameState:
    """검증용 게임 상태를 생성한다."""

    return GameState(
        case_id="CASE-001",
        session_id="ISSUE-22-REAL-DATA",
        unlocked_characters=(
            sorted(EXPECTED_CHARACTER_IDS)
            if unlocked_characters is None
            else unlocked_characters
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


def test_real_npc_count(case001):
    """실제 NPC 10명의 페르소나가 생성되는지 검증한다."""

    personas = case001["personas"]

    assert len(personas) == 10
    assert set(personas) == EXPECTED_CHARACTER_IDS

    for npc_id in EXPECTED_CHARACTER_IDS:
        persona = personas[npc_id]

        assert persona.character_id == npc_id
        assert persona.name.strip()
        assert persona.voice.strip()


def test_real_npc_voice_is_distinct(case001):
    """실제 NPC 10명의 말투 설정이 서로 다른지 확인한다."""

    personas = case001["personas"]

    voices = [persona.voice for persona in personas.values()]

    assert len(set(voices)) == 10, "일부 NPC의 말투 설정이 동일합니다."


def test_real_persona_matches_source(case001):
    """페르소나가 실제 원본의 이름과 말투를 사용하는지 확인한다."""

    personas = case001["personas"]
    characters = case001["characters"]

    for character in characters:
        persona = personas[character.id]

        assert persona.name == character.name.strip()
        assert persona.voice == character.voice.strip()


def test_real_npc_system_prompts(case001):
    """실제 NPC 10명의 시스템 프롬프트를 생성한다."""

    personas = case001["personas"]
    state = make_state()

    prompts = {}

    for npc_id in sorted(EXPECTED_CHARACTER_IDS):
        prompt = build_npc_system_prompt(
            personas,
            active_character_id=npc_id,
            state=state,
        )

        assert prompt
        assert personas[npc_id].name in prompt
        assert personas[npc_id].voice in prompt
        assert f"인물 ID: {npc_id}" in prompt

        prompts[npc_id] = prompt

    # 동일한 기본 규칙을 사용하더라도
    # 인물별 설정이 달라야 한다.
    assert len(set(prompts.values())) == 10


def test_real_npc_behavior_prompts(case001):
    """실제 접근 정책을 적용해 행동 프롬프트를 생성한다."""

    personas = case001["personas"]
    cards = case001["cards"]
    evaluator = case001["evaluator"]

    state = make_state()

    for npc_id in sorted(EXPECTED_CHARACTER_IDS):
        prompt = build_npc_behavior_prompt(
            personas,
            active_character_id=npc_id,
            state=state,
            npc_cards=cards,
            evaluator=evaluator,
        )

        assert prompt
        assert f"인물 ID: {npc_id}" in prompt
        assert personas[npc_id].voice in prompt
        assert "[행동 및 진술 규칙]" in prompt
        assert "[현재 진술 상태]" in prompt


def test_private_profile_fields_not_exposed(case001):
    """관리자 전용 원본 정보가 프롬프트에 복사되지 않는지 검사한다."""

    personas = case001["personas"]
    characters = case001["characters"]
    state = make_state()

    sensitive_fields = (
        "secret_2016",
        "secret_2026",
        "initial",
        "alibi",
        "trajectory",
    )

    for npc_id in sorted(EXPECTED_CHARACTER_IDS):
        prompt = build_npc_system_prompt(
            personas,
            active_character_id=npc_id,
            state=state,
        )

        for character in characters:
            for field_name in sensitive_fields:
                value = getattr(character, field_name).strip()

                # 짧은 일반 표현의 우연한 중복은 제외한다.
                if len(value) < 20:
                    continue

                assert value not in prompt, (
                    f"{npc_id} 프롬프트에 "
                    f"{character.id}의 "
                    f"비공개 필드 {field_name}이 포함되었습니다."
                )


def test_npc_card_content_not_exposed(case001):
    """실제 NPC 지식 카드 원문이 시스템 프롬프트에 삽입되지 않는지 검증한다."""

    personas = case001["personas"]
    cards = case001["cards"]
    evaluator = case001["evaluator"]

    state = make_state()

    for npc_id in sorted(EXPECTED_CHARACTER_IDS):
        prompt = build_npc_behavior_prompt(
            personas,
            active_character_id=npc_id,
            state=state,
            npc_cards=cards,
            evaluator=evaluator,
        )

        for card in cards:
            body = card.get("body")

            if not isinstance(body, str):
                continue

            if len(body.strip()) < 20:
                continue

            assert body.strip() not in prompt, (
                f"{npc_id}의 시스템 프롬프트에 NPC 지식 카드 원문이 포함되었습니다."
            )


def test_locked_npc_blocked(case001):
    """해금되지 않은 NPC의 프롬프트 생성을 차단한다."""

    personas = case001["personas"]
    cards = case001["cards"]
    evaluator = case001["evaluator"]

    state = make_state(unlocked_characters=["C01"])

    for npc_id in sorted(EXPECTED_CHARACTER_IDS):
        if npc_id == "C01":
            continue

        with pytest.raises(PermissionError):
            build_npc_behavior_prompt(
                personas,
                active_character_id=npc_id,
                state=state,
                npc_cards=cards,
                evaluator=evaluator,
            )


def test_invalid_npc_id_rejected(case001):
    """존재하지 않는 NPC ID를 거부한다."""

    personas = case001["personas"]
    state = make_state()

    with pytest.raises(ValueError):
        build_npc_system_prompt(
            personas,
            active_character_id="C11",
            state=state,
        )


def test_real_persona_isolated(case001):
    """NPC별 페르소나가 서로 다른 인물의 설정을 사용하지 않는지 검증한다."""

    personas = case001["personas"]
    state = make_state()

    for npc_id in sorted(EXPECTED_CHARACTER_IDS):
        prompt = build_npc_system_prompt(
            personas,
            active_character_id=npc_id,
            state=state,
        )

        for other_id in EXPECTED_CHARACTER_IDS:
            if other_id == npc_id:
                continue

            assert f"인물 ID: {other_id}" not in prompt
            assert f"이름: {personas[other_id].name}\n" not in prompt
