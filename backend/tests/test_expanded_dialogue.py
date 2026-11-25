"""Issue #165 - reviewed dialogue stage progression."""

from dataclasses import replace

import pytest

from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.expanded_dialogue import (
    ReviewedDialogueBinding,
    apply_reviewed_dialogue,
    validate_source_binding,
)


@pytest.fixture
def binding():
    return ReviewedDialogueBinding(
        source_id="TRG-1120-001",
        source_sha256="a" * 64,
        trigger_id="TRG-TEST-C07",
        card_id="K-C07-01",
        character_id="C07",
        from_stage=1,
        to_stage=2,
        trigger_type="evidence_combo",
        required_evidence=("E11", "E12"),
        required_presentations=("E11", "E12"),
        action_flags=(
            "ACT_C07_STATEMENT_VERIFIED",
        ),
    )


@pytest.fixture
def state():
    initial = create_initial_state(
        "issue165-dialogue",
        content_version="case001_1120",
    )

    return GameState.model_validate({
        **initial.model_dump(),
        "phase": GamePhase.INVESTIGATION,
        "unlocked_characters": ["C01", "C07"],
        "npc_stages": {"C07": 1},
        "evidence": {
            "E11": {"stage": "found"},
            "E12": {"stage": "found"},
        },
        "presented": {"C07": ["E11", "E12"]},
        "disclosed_cards": ["K-C07-01"],
        "score": 2,
    })


def execute(state, binding, **overrides):
    params = {
        "active_character_id": "C07",
        "trigger_ids": ("TRG-TEST-C07",),
        "source_ids": ("K-C07-01",),
        "grounded": True,
        "presented_evidence_id": "E12",
        "bindings": (binding,),
    }

    params.update(overrides)

    return apply_reviewed_dialogue(state, **params)


def test_verified_dialogue_advances_stage(state, binding):
    updated = execute(state, binding)

    assert updated.npc_stages["C07"] == 2
    assert updated.revision == state.revision + 1
    assert "ACT_C07_STATEMENT_VERIFIED" in updated.flags
    assert state.npc_stages["C07"] == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"grounded": False},
        {"trigger_ids": ()},
        {"source_ids": ()},
        {"active_character_id": "C01"},
        {"presented_evidence_id": None},
        {"bindings": ()},
    ],
)
def test_unverified_dialogue_cannot_advance(
    state, binding, overrides,
):
    assert execute(state, binding, **overrides) == state


def test_missing_presentation_denied(state, binding):
    state = state.model_copy(
        update={"presented": {"C07": ["E11"]}}
    )

    assert execute(state, binding) == state


def test_missing_evidence_denied(state, binding):
    state = state.model_copy(
        update={"evidence": {}}
    )

    assert execute(state, binding) == state


def test_missing_disclosed_card_denied(state, binding):
    state = state.model_copy(
        update={"disclosed_cards": []}
    )

    assert execute(state, binding) == state


def test_legacy_content_unchanged(state, binding):
    legacy = state.model_copy(
        update={"content_version": "case001_v7_1"}
    )

    assert execute(legacy, binding) == legacy


def test_duplicate_execution_is_idempotent(state, binding):
    updated = execute(state, binding)

    assert execute(updated, binding) == updated


def test_stage_skip_rejected(binding):
    with pytest.raises(ValueError):
        replace(binding, to_stage=3)


def test_consent_flag_cannot_be_granted(binding):
    with pytest.raises(ValueError):
        replace(
            binding,
            action_flags=("consent_and_safety_verified",),
        )


def test_cross_npc_action_rejected(binding):
    with pytest.raises(ValueError):
        replace(
            binding,
            action_flags=(
                "ACT_C05_INTERVIEW_COMPLETED",
            ),
        )


def test_source_hash_mismatch_rejected(binding):
    source = {
        "source_id": binding.source_id,
        "source_sha256": "b" * 64,
        "character_id": binding.character_id,
        "stage": binding.from_stage,
        "next_stage": binding.to_stage,
        "trigger_type": binding.trigger_type,
    }

    with pytest.raises(ValueError):
        validate_source_binding(binding, source)
