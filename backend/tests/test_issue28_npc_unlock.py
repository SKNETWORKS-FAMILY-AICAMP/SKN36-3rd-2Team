import pytest

from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.npc_unlock import (
    NPCUnlockRule,
    find_unlockable_npcs,
)
from crimescene.scenario.schemas.game_state import EvidenceState


def test_unlock_by_evidence():
    state = create_initial_state("test-session")

    rules = {"C02": NPCUnlockRule(required_evidence=frozenset({"E01"}))}

    assert find_unlockable_npcs(state, rules) == ()

    state = state.model_copy(update={"evidence": {"E01": EvidenceState(stage="found")}})

    assert find_unlockable_npcs(state, rules) == ("C02",)


def test_unlock_requires_all_conditions():
    state = create_initial_state("test-session")

    rules = {
        "C02": NPCUnlockRule(
            required_evidence=frozenset({"E01"}),
            required_flags=frozenset({"INVESTIGATED"}),
        )
    }

    state = state.model_copy(update={"evidence": {"E01": EvidenceState(stage="found")}})

    assert find_unlockable_npcs(state, rules) == ()

    state = state.model_copy(update={"flags": ["INVESTIGATED"]})

    assert find_unlockable_npcs(state, rules) == ("C02",)


def test_already_unlocked_npc_is_excluded():
    state = create_initial_state("test-session")

    state = state.model_copy(
        update={
            "unlocked_characters": ["C01", "C02"],
            "evidence": {"E01": EvidenceState(stage="found")},
        }
    )

    rules = {"C02": NPCUnlockRule(required_evidence=frozenset({"E01"}))}

    assert find_unlockable_npcs(state, rules) == ()


def test_unknown_npc_is_rejected():
    state = create_initial_state("test-session")

    rules = {"C99": NPCUnlockRule(required_evidence=frozenset({"E01"}))}

    with pytest.raises(ValueError):
        find_unlockable_npcs(state, rules)


def test_empty_unlock_rule_is_rejected():
    state = create_initial_state("test-session")

    with pytest.raises(ValueError):
        find_unlockable_npcs(
            state,
            {"C02": NPCUnlockRule()},
        )


def test_unlock_requires_evidence_presentation():
    state = create_initial_state("test-session")

    rules = {"C02": NPCUnlockRule(required_presentations=frozenset({"C01:E01"}))}

    state = state.model_copy(update={"evidence": {"E01": EvidenceState(stage="found")}})

    assert find_unlockable_npcs(state, rules) == ()

    state = state.model_copy(update={"presented": {"C01": ["E01"]}})

    assert find_unlockable_npcs(state, rules) == ("C02",)
