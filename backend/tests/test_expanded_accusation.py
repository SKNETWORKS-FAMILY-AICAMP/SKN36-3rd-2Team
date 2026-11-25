"""Issue #165 - expanded catalog accusation requirements."""

import pytest

from crimescene.scenario.accusation import (
    can_accuse,
    enter_accusation,
)
from crimescene.scenario.content_compiler import PROPOSED_SCORES
from crimescene.scenario.evidence_collection import get_collection_progress
from crimescene.scenario.game_progress import (
    create_initial_state,
    meets_accusation_requirements,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase, GameState

LEGACY_SCORES = dict(
    zip(
        [f"E{i:02d}" for i in range(1, 11)],
        [1, 2, 3, 2, 3, 3, 2, 2, 1, 2],
        strict=True,
    )
)


@pytest.fixture
def expanded_rules():
    return {
        eid: EvidenceRule(
            name=f"Evidence {eid}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for eid, score in {
            **LEGACY_SCORES,
            **PROPOSED_SCORES,
        }.items()
    }


def make_state(rules, evidence=()):
    state = create_initial_state("issue165-accusation")

    return GameState.model_validate({
        **state.model_dump(),
        "phase": GamePhase.INVESTIGATION,
        "evidence": {
            eid: {"stage": "found"}
            for eid in evidence
        },
        "score": sum(
            rules[eid].score for eid in evidence
        ),
    })


def highest_scoring(rules, count):
    return sorted(
        rules,
        key=lambda eid: rules[eid].score,
        reverse=True,
    )[:count]


def test_expanded_catalog_total(expanded_rules):
    state = make_state(expanded_rules)

    progress = get_collection_progress(
        state, expanded_rules
    )

    assert progress.total == 65
    assert progress.total_count == 30


def test_initial_state_cannot_accuse(expanded_rules):
    assert not can_accuse(
        make_state(expanded_rules),
        expanded_rules,
    )


def test_fifteen_high_value_evidence_allow_accusation(
    expanded_rules,
):
    ids = highest_scoring(expanded_rules, 15)

    state = make_state(expanded_rules, ids)

    assert state.score >= 33
    assert can_accuse(state, expanded_rules)


def test_fourteen_evidence_are_insufficient(
    expanded_rules,
):
    ids = highest_scoring(expanded_rules, 14)

    state = make_state(expanded_rules, ids)

    assert state.score >= 33
    assert not can_accuse(state, expanded_rules)


def test_fifteen_low_value_evidence_are_insufficient(
    expanded_rules,
):
    ids = sorted(
        expanded_rules,
        key=lambda eid: expanded_rules[eid].score,
    )[:15]

    state = make_state(expanded_rules, ids)

    assert state.score < 33
    assert not can_accuse(state, expanded_rules)


def test_all_thirty_evidence_are_valid(expanded_rules):
    state = make_state(
        expanded_rules,
        list(expanded_rules),
    )

    assert state.score == 65
    assert can_accuse(state, expanded_rules)


def test_score_tampering_rejected(expanded_rules):
    state = make_state(expanded_rules)

    state = state.model_copy(update={"score": 65})

    with pytest.raises(ValueError):
        can_accuse(state, expanded_rules)


def test_incomplete_catalog_rejected(expanded_rules):
    state = make_state(expanded_rules)

    del expanded_rules["E30"]

    with pytest.raises(ValueError):
        can_accuse(state, expanded_rules)


def test_legacy_catalog_remains_supported(expanded_rules):
    rules = {
        eid: expanded_rules[eid]
        for eid in LEGACY_SCORES
    }

    state = make_state(rules, list(rules))

    assert state.score == 21
    assert can_accuse(state, rules)


def test_extended_accusation_phase_transition(
    expanded_rules,
):
    ids = highest_scoring(expanded_rules, 15)

    state = make_state(expanded_rules, ids)

    updated = enter_accusation(state, expanded_rules)

    assert updated.phase == GamePhase.ACCUSATION
    assert updated.revision == state.revision + 1


def test_extended_evidence_counted_in_requirement(
    expanded_rules,
):
    ids = highest_scoring(expanded_rules, 15)

    state = make_state(expanded_rules, ids)

    assert meets_accusation_requirements(
        state,
        expanded_rules,
    )
