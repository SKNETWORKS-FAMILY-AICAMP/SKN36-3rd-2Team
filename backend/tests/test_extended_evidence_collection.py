"""Issue #165 - extended evidence collection integration."""

import pytest

from crimescene.scenario.acquisition_policy import (
    AcquisitionPolicy,
    AcquisitionRoute,
)
from crimescene.scenario.evidence_collection import collect_evidence
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase, GameState


def make_access_policy(required_evidence=()):
    return AccessPolicy(
        required_evidence=list(required_evidence),
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character="C01",
    )


@pytest.fixture
def evidence_rules():
    return {
        eid: EvidenceRule(
            name=f"Test {eid}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for eid, score in [
            ("E11", 1),
            ("E12", 2),
        ]
    }


@pytest.fixture
def approved_routes():
    return {
        "E12": AcquisitionPolicy(
            evidence_id="E12",
            routes=[
                AcquisitionRoute(
                    route_id="PRIMARY",
                    chapter="CH01",
                    action_flag="ACT_PRIMARY_VERIFIED",
                    policy=make_access_policy(["E11"]),
                ),
                AcquisitionRoute(
                    route_id="ALTERNATIVE",
                    chapter="CH01",
                    action_flag="ACT_ALTERNATIVE_VERIFIED",
                    policy=make_access_policy(),
                ),
            ],
        ),
    }


def make_state(*, evidence=(), flags=()):
    state = create_initial_state("issue165-collection")

    return GameState.model_validate({
        **state.model_dump(),
        "phase": GamePhase.INVESTIGATION,
        "current_chapter": "CH01",
        "unlocked_chapters": ["CH00", "CH01"],
        "evidence": {
            eid: {"stage": "found"}
            for eid in evidence
        },
        "flags": list(flags),
        "score": len(evidence),
    })


def collect(state, rules, routes):
    return collect_evidence(
        state=state,
        evidence_id="E12",
        evidence_rules=rules,
        acquisition_policy_ids={
            "E12": "POL-LEGACY",
        },
        evaluator=PolicyEvaluator({
            "POL-LEGACY": make_access_policy(),
        }),
        active_character_id="C01",
        approved_routes=routes,
    )


def test_primary_route_collects_evidence(
    evidence_rules,
    approved_routes,
):
    state = make_state(
        evidence=["E11"],
        flags=["ACT_PRIMARY_VERIFIED"],
    )

    result = collect(
        state,
        evidence_rules,
        approved_routes,
    )

    assert result.created is True
    assert "E12" in result.state.evidence
    assert result.state.score == 3
    assert result.state.revision == state.revision + 1
    assert result.progress.total == 3
    assert result.progress.collected_count == 2
    assert "E12" not in state.evidence


def test_alternative_route_collects_evidence(
    evidence_rules,
    approved_routes,
):
    state = make_state(
        flags=["ACT_ALTERNATIVE_VERIFIED"],
    )

    result = collect(
        state,
        evidence_rules,
        approved_routes,
    )

    assert result.created is True
    assert result.state.score == 2
    assert "E12" in result.state.evidence


def test_unapproved_route_cannot_use_legacy_policy(
    evidence_rules,
):
    state = make_state(
        flags=["ACT_ALTERNATIVE_VERIFIED"],
    )

    with pytest.raises(PermissionError):
        collect(state, evidence_rules, None)


def test_missing_action_rejected(
    evidence_rules,
    approved_routes,
):
    state = make_state(evidence=["E11"])

    with pytest.raises(PermissionError):
        collect(state, evidence_rules, approved_routes)


def test_missing_prerequisite_rejected(
    evidence_rules,
    approved_routes,
):
    state = make_state(
        flags=["ACT_PRIMARY_VERIFIED"],
    )

    with pytest.raises(PermissionError):
        collect(state, evidence_rules, approved_routes)


def test_wrong_policy_id_rejected(
    evidence_rules,
    approved_routes,
):
    state = make_state(
        flags=["ACT_ALTERNATIVE_VERIFIED"],
    )

    routes = {
        "E12": approved_routes["E12"].model_copy(
            update={"evidence_id": "E13"},
        ),
    }

    with pytest.raises(PermissionError):
        collect(state, evidence_rules, routes)


def test_duplicate_collection_does_not_increase_score(
    evidence_rules,
    approved_routes,
):
    state = make_state(
        flags=["ACT_ALTERNATIVE_VERIFIED"],
    )

    first = collect(
        state,
        evidence_rules,
        approved_routes,
    )

    second = collect(
        first.state,
        evidence_rules,
        approved_routes,
    )

    assert second.created is False
    assert second.state == first.state
    assert second.state.score == 2
