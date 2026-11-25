"""Issue #165 - presentation-driven NPC stage entry."""

import pytest

from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.npc_stage_rules import (
    PresentationStageRule,
    apply_presentation_stage,
    compile_stage_candidates,
    load_approved_stage_rules,
)


@pytest.fixture
def state():
    initial = create_initial_state(
        "issue165-stage",
        content_version="case001_1120",
    )

    return GameState.model_validate({
        **initial.model_dump(),
        "phase": GamePhase.INVESTIGATION,
        "unlocked_characters": ["C01", "C03"],
        "evidence": {
            "E21": {"stage": "found"},
            "E23": {"stage": "found"},
        },
        "presented": {"C03": ["E21", "E23"]},
    })


@pytest.fixture
def rules():
    return (
        PresentationStageRule(
            source_id="TRG-1120-001",
            source_sha256="a" * 64,
            character_id="C03",
            target_stage=2,
            evidence_ids=frozenset({"E21"}),
        ),
        PresentationStageRule(
            source_id="TRG-1120-002",
            source_sha256="b" * 64,
            character_id="C03",
            target_stage=3,
            evidence_ids=frozenset({"E21", "E23"}),
        ),
    )


def apply(state, rules, eid="E23", npc="C03"):
    return apply_presentation_stage(
        state,
        active_character_id=npc,
        presented_evidence_id=eid,
        rules=rules,
    )


def test_valid_combo_enters_stage_three(state, rules):
    result = apply(state, rules)

    assert result.npc_stages["C03"] == 3
    assert result.revision == state.revision + 1
    assert state.npc_stages == {}


def test_single_evidence_enters_stage_two(state, rules):
    state = state.model_copy(update={
        "presented": {"C03": ["E21"]},
    })

    result = apply(state, rules, eid="E21")

    assert result.npc_stages["C03"] == 2


def test_uncollected_evidence_cannot_enter_stage_three(state, rules):
    state = state.model_copy(update={
        "evidence": {
            "E21": state.evidence["E21"],
        },
    })

    assert apply(state, rules) == state


def test_other_npc_presentation_does_not_count(state, rules):
    state = state.model_copy(update={
        "presented": {"C01": ["E21", "E23"]},
    })

    assert apply(state, rules) == state


def test_no_presentation_no_transition(state, rules):
    assert apply(state, rules, eid=None) == state


def test_no_approval_no_transition(state):
    assert apply(state, ()) == state


def test_stage_does_not_decrease(state, rules):
    state = state.model_copy(update={
        "npc_stages": {"C03": 3},
        "presented": {"C03": ["E21"]},
    })

    assert apply(state, rules, eid="E21") == state


def test_stage_does_not_repeat(state, rules):
    updated = apply(state, rules)

    assert apply(updated, rules) == updated


def test_legacy_runtime_unchanged(state, rules):
    state = state.model_copy(update={
        "content_version": "case001_v7_1",
    })

    assert apply(state, rules) == state


def source_row(condition="always", evidence="E21+E23"):
    return {
        "source_id": "TRG-1120-001",
        "source_sha256": "a" * 64,
        "character_id": "C03",
        "stage": 3,
        "next_stage": 3,
        "trigger_type": "evidence_combo",
        "condition_key": condition,
        "source_evidence_ids": evidence,
    }


def test_source_target_stage_compiled():
    result = compile_stage_candidates([source_row()])

    assert len(result) == 1
    assert result[0].target_stage == 3


@pytest.mark.parametrize(
    "condition",
    [
        "E01_acknowledged",
        "E14_not_acknowledged",
        "consent_and_safety_verified",
    ],
)
def test_complex_conditions_require_review(condition):
    assert not compile_stage_candidates([
        source_row(condition)
    ])


def test_e30_excluded():
    assert not compile_stage_candidates([
        source_row(evidence="E18+E30")
    ])


def test_approval_requires_source_hash():
    row = source_row()

    with pytest.raises(ValueError):
        load_approved_stage_rules(
            [row],
            {row["source_id"]: "b" * 64},
        )


def test_explicit_valid_approval():
    row = source_row()

    result = load_approved_stage_rules(
        [row],
        {row["source_id"]: row["source_sha256"]},
    )

    assert len(result) == 1


def test_empty_approval_remains_disabled():
    assert not load_approved_stage_rules(
        [source_row()],
        {},
    )
