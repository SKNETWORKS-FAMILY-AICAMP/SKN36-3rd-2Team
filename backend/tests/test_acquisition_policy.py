"""Issue #165 - alternative evidence acquisition routes."""

from crimescene.scenario.acquisition_policy import (
    AcquisitionPolicy,
    AcquisitionRoute,
    allows_acquisition,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GamePhase, GameState


def make_policy(required_evidence):
    return AccessPolicy(
        required_evidence=required_evidence,
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character=None,
    )


def make_acquisition_policy():
    return AcquisitionPolicy(
        evidence_id="E12",
        routes=[
            AcquisitionRoute(
                route_id="ROUTE-A",
                chapter="CH01",
                action_flag="ACT_SOURCE_VERIFIED",
                policy=make_policy(["E11"]),
            ),
            AcquisitionRoute(
                route_id="ROUTE-B",
                chapter="CH01",
                action_flag="ACT_ALTERNATIVE_VERIFIED",
                policy=make_policy([]),
            ),
        ],
    )


def make_state(*, flags=(), evidence=()):
    initial = create_initial_state("issue165-test")

    return GameState.model_validate({
        **initial.model_dump(),
        "phase": GamePhase.INVESTIGATION,
        "current_chapter": "CH01",
        "unlocked_chapters": ["CH00", "CH01"],
        "flags": list(flags),
        "evidence": {
            eid: {"stage": "found"}
            for eid in evidence
        },
    })


def test_primary_route():
    state = make_state(
        flags=["ACT_SOURCE_VERIFIED"],
        evidence=["E11"],
    )
    assert allows_acquisition(make_acquisition_policy(), state)


def test_alternative_route():
    state = make_state(
        flags=["ACT_ALTERNATIVE_VERIFIED"],
    )
    assert allows_acquisition(make_acquisition_policy(), state)


def test_missing_action_denied():
    state = make_state(evidence=["E11"])
    assert not allows_acquisition(make_acquisition_policy(), state)


def test_missing_prerequisite_denied():
    state = make_state(flags=["ACT_SOURCE_VERIFIED"])
    assert not allows_acquisition(make_acquisition_policy(), state)


def test_locked_chapter_denied():
    state = create_initial_state("issue165-locked")
    state = state.model_copy(update={
        "phase": GamePhase.INVESTIGATION,
        "flags": ["ACT_ALTERNATIVE_VERIFIED"],
    })
    assert not allows_acquisition(make_acquisition_policy(), state)
