import pytest

from crimescene.api.story_event_conditions import (
    StoryEventConditions,
    matches_story_event_prerequisites,
)
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)


def make_state(
    *,
    evidence=("E19",),
    flags=("TEST_OFFICE_ACCESS_VERIFIED",),
    chapter="CH01",
    phase=GamePhase.INVESTIGATION,
    case_id="CASE-001",
    outcome=None,
):
    chapter_number = int(chapter[-1])

    return GameState(
        case_id=case_id,
        session_id="test-story-session",
        phase=phase,
        current_chapter=chapter,
        unlocked_chapters=[f"CH{i:02d}" for i in range(chapter_number + 1)],
        unlocked_characters=["C01"],
        evidence={item: EvidenceState(stage="found") for item in evidence},
        flags=list(flags),
        presented={},
        attempts_left=3,
        score=0,
        outcome=outcome,
        deep_eligible=False,
        revision=1,
        disclosed_cards=[],
        document_grants=[],
    )


def office_event():
    return StoryEventConditions(
        story_id="STORY_020",
        chapter="CH01",
        all_evidence=frozenset({"E19"}),
        required_flags=frozenset(
            {
                "TEST_OFFICE_ACCESS_VERIFIED",
            }
        ),
    )


def test_valid_story_event_prerequisites():
    assert matches_story_event_prerequisites(office_event(), make_state())


def test_missing_required_evidence_is_denied():
    assert not matches_story_event_prerequisites(
        office_event(), make_state(evidence=())
    )


def test_missing_server_action_is_denied():
    assert not matches_story_event_prerequisites(office_event(), make_state(flags=()))


def test_wrong_chapter_is_denied():
    assert not matches_story_event_prerequisites(
        office_event(), make_state(chapter="CH02")
    )


def test_prologue_is_denied():
    # Match the rule's chapter so only the PROLOGUE guard is tested.
    rule = StoryEventConditions(
        story_id="STORY_020",
        chapter="CH00",
        all_evidence=frozenset({"E19"}),
        required_flags=frozenset({"TEST_OFFICE_ACCESS_VERIFIED"}),
    )

    assert not matches_story_event_prerequisites(
        rule,
        make_state(chapter="CH00", phase=GamePhase.PROLOGUE),
    )


def test_other_case_is_denied():
    assert not matches_story_event_prerequisites(
        office_event(), make_state(case_id="OTHER-CASE")
    )


def test_finished_game_is_denied():
    assert not matches_story_event_prerequisites(
        office_event(), make_state(phase=GamePhase.FINISHED)
    )


@pytest.mark.parametrize(
    "evidence",
    [
        ("E21",),
        ("E22",),
        ("E21", "E22"),
    ],
)
def test_evidence_or_condition(evidence):
    rule = StoryEventConditions(
        story_id="STORY_023",
        chapter="CH03",
        any_evidence=frozenset({"E21", "E22"}),
        required_flags=frozenset(
            {
                "TEST_FACILITY_LOOKUP_VERIFIED",
            }
        ),
    )

    state = make_state(
        chapter="CH03",
        evidence=evidence,
        flags=("TEST_FACILITY_LOOKUP_VERIFIED",),
    )

    assert matches_story_event_prerequisites(rule, state)


def test_evidence_or_condition_denies_missing_inputs():
    rule = StoryEventConditions(
        story_id="STORY_023",
        chapter="CH03",
        any_evidence=frozenset({"E21", "E22"}),
        required_flags=frozenset(
            {
                "TEST_FACILITY_LOOKUP_VERIFIED",
            }
        ),
    )

    state = make_state(
        chapter="CH03",
        evidence=("E01",),
        flags=("TEST_FACILITY_LOOKUP_VERIFIED",),
    )

    assert not matches_story_event_prerequisites(rule, state)


def test_evidence_only_rule_is_rejected():
    with pytest.raises(ValueError):
        StoryEventConditions(
            story_id="STORY_020",
            chapter="CH01",
            all_evidence=frozenset({"E19"}),
        )


def test_deep_ending_requires_separate_gate():
    with pytest.raises(ValueError):
        StoryEventConditions(
            story_id="STORY_030",
            chapter="CH04",
            all_evidence=frozenset({"E30"}),
            required_flags=frozenset({"TEST_CONSENT_VERIFIED"}),
        )
