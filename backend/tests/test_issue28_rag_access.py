"""Issue #28 - 플래그 지급 전후 RAG 정보 접근 검증."""

import pytest

from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.loaders.unlock_graph_loader import (
    Case001UnlockRules,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.rag_access import build_authorized_rag_context
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)
from crimescene.trigger.evidence_presentation import (
    process_npc_dialogue_event,
)

POLICY_ID = "POL-ISSUE28-L03"

POLICY = AccessPolicy(
    required_evidence=["E05"],
    required_presentations=["C03:E05"],
    required_flags=["L03"],
    required_ending=None,
    required_topics=[],
    required_disclosed_cards=[],
    required_character="C03",
)

CARD = {
    **POLICY.model_dump(),
    "id": "K-C03-ISSUE28",
    "case_id": "CASE-001",
    "character_id": "C03",
    "policy_id": POLICY_ID,
    "body": "접근 권한 검증용 NPC 지식",
    "access_scope": "character_only",
    "truth_status": "character_claim",
    "supersedes": [],
    "stage_priority": 1,
}

CONFIG = Case001UnlockRules(
    npc_rules={},
    flag_requirements={"L03": frozenset({"E05"})},
    flag_sources={"L03": "C03 P:E05"},
)


def make_state():
    return create_initial_state("issue28-rag").model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "unlocked_characters": ["C01", "C03"],
            "evidence": {
                "E05": EvidenceState(stage="found"),
            },
            "score": 3,
        }
    )


def authorized_cards(state, *, npc="C03", policies=None):
    if policies is None:
        policies = {POLICY_ID: POLICY}

    return build_authorized_rag_context(
        documents=[],
        npc_cards=[CARD],
        state=state,
        evaluator=PolicyEvaluator(policies),
        active_character_id=npc,
    )


def present_evidence(state):
    return process_npc_dialogue_event(
        "증거를 확인해주세요.",
        state=state,
        active_character_id="C03",
        trigger_rules=(),
        evaluator=PolicyEvaluator({}),
        evidence_rules={
            "E05": EvidenceRule(
                name="테스트 증거",
                score=3,
                holder="C03",
                prerequisites=[],
                presentation=[],
                q=[],
            )
        },
        allowed_recipients={
            "E05": frozenset({"C03"}),
        },
        presented_evidence_id="E05",
        flag_config=CONFIG,
    )


def test_rag_unlock_after_verified_presentation():
    state = make_state()

    # 증거만 보유한 상태에서는 접근할 수 없습니다.
    assert authorized_cards(state) == []

    result = present_evidence(state)

    assert result.state.flags == ["L03"]
    assert result.state.presented == {"C03": ["E05"]}

    # 승인된 이벤트 이후에만 NPC 지식이 공개됩니다.
    cards = authorized_cards(result.state)

    assert [card.source_id for card in cards] == ["K-C03-ISSUE28"]


def test_flag_alone_cannot_bypass_presentation():
    state = make_state().model_copy(update={"flags": ["L03"]})

    assert authorized_cards(state) == []


def test_other_npc_cannot_access_knowledge():
    state = present_evidence(make_state()).state

    assert authorized_cards(state, npc="C01") == []


def test_missing_policy_fails_closed():
    state = present_evidence(make_state()).state

    assert authorized_cards(state, policies={}) == []


def test_uncollected_evidence_blocks_event():
    state = make_state().model_copy(
        update={
            "evidence": {},
            "score": 0,
        }
    )

    with pytest.raises(PermissionError):
        present_evidence(state)

    assert authorized_cards(state) == []
