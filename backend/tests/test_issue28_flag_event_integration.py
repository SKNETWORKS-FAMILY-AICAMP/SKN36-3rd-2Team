import pytest

from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.loaders.unlock_graph_loader import (
    Case001UnlockRules,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)
from crimescene.trigger.evidence_presentation import (
    process_npc_dialogue_event,
)
from crimescene.trigger.npc_trigger import NPCTriggerRule


def make_state(*, collected=True):
    state = create_initial_state("issue28-event")

    return state.model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "unlocked_characters": ["C01", "C03"],
            "evidence": ({"E05": EvidenceState(stage="found")} if collected else {}),
            "score": 3 if collected else 0,
        }
    )


def make_config():
    return Case001UnlockRules(
        npc_rules={},
        flag_requirements={
            "L03": frozenset({"E05"}),
        },
        flag_sources={
            "L03": "C03 P:E05",
        },
    )


def make_evidence():
    return {
        "E05": EvidenceRule(
            name="테스트 증거",
            score=3,
            holder="C03",
            prerequisites=[],
            presentation=[],
            q=[],
        )
    }


def run_event(
    state,
    *,
    presented=None,
    trigger_rules=(),
):
    return process_npc_dialogue_event(
        "증거를 확인해주세요.",
        state=state,
        active_character_id="C03",
        trigger_rules=trigger_rules,
        evaluator=PolicyEvaluator({}),
        evidence_rules=make_evidence(),
        allowed_recipients={
            "E05": frozenset({"C03"}),
        },
        presented_evidence_id=presented,
        flag_config=make_config(),
    )


def test_presentation_grants_l03():
    result = run_event(
        make_state(),
        presented="E05",
    )

    assert result.presentation_created is True
    assert result.state.presented == {"C03": ["E05"]}
    assert result.state.flags == ["L03"]


def test_no_presentation_no_flag():
    result = run_event(make_state())

    assert result.presentation_created is False
    assert result.state.flags == []


def test_uncollected_evidence_is_blocked():
    with pytest.raises(PermissionError):
        run_event(
            make_state(collected=False),
            presented="E05",
        )


def test_duplicate_presentation_is_idempotent():
    first = run_event(
        make_state(),
        presented="E05",
    )

    second = run_event(
        first.state,
        presented="E05",
    )

    assert second.presentation_created is False
    assert second.state.flags == ["L03"]
    assert second.state.revision == first.state.revision


def test_direct_flag_grant_is_blocked():
    trigger = NPCTriggerRule(
        trigger_id="TRG-INVALID-FLAG",
        character_id="C03",
        policy_id="POL-TEST",
        topic="test",
        phrases=("증거",),
        grant_flags=("L03",),
    )

    with pytest.raises(ValueError, match="직접 지급"):
        run_event(
            make_state(),
            trigger_rules=(trigger,),
        )
