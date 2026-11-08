"""#22 NPC 행동 규칙: 기존 GameState/정책 검증을 통과한 진술만 사용한다."""

import pytest

from crimescene.chat.npc_behavior import build_npc_behavior_prompt
from crimescene.chat.npc_persona import NPCPersona
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import EvidenceState, GameState


def _state(*, unlocked=None, evidence=None, case_id="CASE-001") -> GameState:
    return GameState(
        case_id=case_id,
        session_id="TEST-BEHAVIOR",
        unlocked_characters=["C01", "C02"] if unlocked is None else unlocked,
        evidence={} if evidence is None else evidence,
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


def _policy(*, character="C01", evidence=(), topics=()):
    return AccessPolicy(
        required_evidence=list(evidence),
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=list(topics),
        required_disclosed_cards=[],
        required_character=character,
    )


def _card(
    card_id,
    *,
    character="C01",
    policy_id="POL-OPEN",
    status="character_claim",
    supersedes=(),
    priority=0,
    content="비공개 원문 TEST_PRIVATE_CONTENT",
    topics=(),
):
    return {
        "id": card_id,
        "case_id": "CASE-001",
        "character_id": character,
        "policy_id": policy_id,
        "body": content,
        "access_scope": "character_only",
        "truth_status": status,
        "required_evidence": [],
        "required_presentations": [],
        "required_flags": [],
        "required_ending": None,
        "required_topics": list(topics),
        "required_disclosed_cards": [],
        "required_character": character,
        "supersedes": list(supersedes),
        "stage_priority": priority,
    }


@pytest.fixture
def personas():
    return {
        "C01": NPCPersona("C01", "테스트 인물 1", "조심스럽고 말을 아낀다"),
        "C02": NPCPersona("C02", "테스트 인물 2", "단호하고 빠르게 말한다"),
    }


def _prompt(
    personas,
    *,
    npc_id="C01",
    state=None,
    cards=(),
    policies=None,
    topics=(),
):
    return build_npc_behavior_prompt(
        personas,
        active_character_id=npc_id,
        state=_state() if state is None else state,
        npc_cards=cards,
        evaluator=PolicyEvaluator({} if policies is None else policies),
        matched_topics=topics,
    )


def test_no_authorized_card_requires_avoidance(personas):
    prompt = _prompt(personas)
    assert "승인된 진술이 없습니다" in prompt
    assert "새로운 거짓 진술" in prompt


def test_character_claim_is_not_equated_with_confirmed_lie(personas):
    prompt = _prompt(
        personas,
        cards=[_card("K-CLAIM")],
        policies={"POL-OPEN": _policy()},
    )
    assert "공개 가능한 주장(character_claim)" in prompt
    assert "참인지 거짓인지 임의로 결정하지 마세요" in prompt
    assert "TEST_PRIVATE_CONTENT" not in prompt
    assert "K-CLAIM" not in prompt


def test_known_information_keeps_uncertainty(personas):
    prompt = _prompt(
        personas,
        cards=[_card("K-KNOWN", status="known_to_character")],
        policies={"POL-OPEN": _policy()},
    )
    assert "공개 가능한 지식(known_to_character)" in prompt
    assert "객관적으로 확정된 사건 사실로 단정하지 마세요" in prompt


def test_known_and_claimed_information_are_separate(personas):
    prompt = _prompt(
        personas,
        cards=[
            _card("K-CLAIM"),
            _card("K-KNOWN", status="known_to_character"),
        ],
        policies={"POL-OPEN": _policy()},
    )
    assert "모두 있습니다" in prompt
    assert "주장을 확인된 사실에 섞어" in prompt


def test_unapproved_policy_cannot_change_behavior(personas):
    prompt = _prompt(personas, cards=[_card("K-SECRET")])
    assert "승인된 진술이 없습니다" in prompt
    assert "TEST_PRIVATE_CONTENT" not in prompt


def test_other_npc_knowledge_is_not_used(personas):
    prompt = _prompt(
        personas,
        cards=[_card("K-OTHER", character="C02", policy_id="POL-OTHER")],
        policies={"POL-OTHER": _policy(character="C02")},
    )
    assert "승인된 진술이 없습니다" in prompt
    assert "K-OTHER" not in prompt
    assert "테스트 인물 2" not in prompt


def test_npc_personas_remain_distinct(personas):
    first = _prompt(personas)
    second = _prompt(personas, npc_id="C02")
    assert "조심스럽고 말을 아낀다" in first
    assert "단호하고 빠르게 말한다" in second
    assert "단호하고 빠르게 말한다" not in first
    assert "조심스럽고 말을 아낀다" not in second


def test_evidence_condition_changes_statement_mode(personas):
    policies = {
        "POL-OPEN": _policy(),
        "POL-LOCKED": _policy(evidence=["E05"]),
    }
    cards = [
        _card("K-OLD"),
        _card(
            "K-NEW",
            policy_id="POL-LOCKED",
            status="known_to_character",
            supersedes=["K-OLD"],
            priority=2,
        ),
    ]
    before = _prompt(personas, cards=cards, policies=policies)
    after = _prompt(
        personas,
        cards=cards,
        policies=policies,
        state=_state(evidence={"E05": EvidenceState(stage="found")}),
    )
    assert "공개 가능한 주장(character_claim)" in before
    assert "공개 가능한 지식(known_to_character)" in after
    assert "공개 가능한 주장(character_claim) 유형의 진술이 있습니다" not in after


def test_question_topic_is_policy_guarded(personas):
    policies = {"POL-TOPIC": _policy(topics=["알리바이"])}
    cards = [_card("K-TOPIC", policy_id="POL-TOPIC", topics=["알리바이"])]
    blocked = _prompt(personas, cards=cards, policies=policies)
    allowed = _prompt(personas, cards=cards, policies=policies, topics=["알리바이"])
    assert "승인된 진술이 없습니다" in blocked
    assert "공개 가능한 주장(character_claim)" in allowed


def test_locked_npc_rejected(personas):
    with pytest.raises(PermissionError, match="잠긴 NPC"):
        _prompt(personas, state=_state(unlocked=[]))


def test_invalid_npc_rejected(personas):
    with pytest.raises(ValueError, match="유효하지 않은 NPC ID"):
        _prompt(personas, npc_id="C11")


def test_wrong_case_rejected(personas):
    with pytest.raises(ValueError, match="사건 ID"):
        _prompt(personas, state=_state(case_id="OTHER"))


def test_invalid_evaluator_rejected(personas):
    with pytest.raises(TypeError, match="PolicyEvaluator"):
        build_npc_behavior_prompt(
            personas,
            active_character_id="C01",
            state=_state(),
            npc_cards=[],
            evaluator=None,
        )


def test_malformed_card_fail_closed(personas):
    malformed = {"id": "K-MALFORMED", "body": "SECRET_SHOULD_NOT_LEAK"}
    prompt = _prompt(
        personas,
        cards=[malformed],
        policies={"POL-OPEN": _policy()},
    )
    assert "승인된 진술이 없습니다" in prompt
    assert "SECRET_SHOULD_NOT_LEAK" not in prompt


def test_raw_card_text_never_enters_system_prompt(personas):
    secret = "CONFIDENTIAL_NPC_PRIVATE_FACT"
    prompt = _prompt(
        personas,
        cards=[_card("K-A", content=secret)],
        policies={"POL-OPEN": _policy()},
    )
    assert secret not in prompt
    assert "K-A" not in prompt


def test_invalid_topics_type_rejected(personas):
    with pytest.raises(TypeError, match="질문 주제"):
        _prompt(personas, topics="알리바이")


def test_real_case001_persona_and_policy_integration():
    """관리자 원본이 있으면 실제 NPC 10명과 153개 접근 정책을 활용한다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / ".local" / "case001_v7_1"
    if not root.exists():
        pytest.skip("로컬 CASE-001 관리자 데이터가 없습니다.")

    from crimescene.chat.npc_persona import load_npc_personas
    from crimescene.ingest.case001_dataset import load_npc_cards
    from crimescene.scenario.loaders.access_policy_loader import (
        load_access_policies,
    )

    characters = list(root.glob("*/data/characters.json"))
    cards = list(root.rglob("npc_knowledge_cards.jsonl"))
    policies = list(root.rglob("access_policies.json"))
    assert len(characters) == len(cards) == len(policies) == 1

    personas = load_npc_personas(characters[0])
    npc_cards = load_npc_cards(cards[0])
    evaluator = PolicyEvaluator(load_access_policies(policies[0]))
    unlocked_ids = sorted(personas)
    state = _state(unlocked=unlocked_ids)

    prompts = []
    for npc_id in unlocked_ids:
        prompt = build_npc_behavior_prompt(
            personas,
            active_character_id=npc_id,
            state=state,
            npc_cards=npc_cards,
            evaluator=evaluator,
        )
        assert personas[npc_id].voice in prompt
        assert "[행동 및 진술 규칙]" in prompt
        assert "[현재 진술 상태]" in prompt
        prompts.append(prompt)

    assert len(prompts) == len(set(prompts)) == 10
