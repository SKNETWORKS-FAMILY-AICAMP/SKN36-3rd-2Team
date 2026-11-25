"""Issue #165 - versioned chapter and NPC stage policies."""

import pytest
from pydantic import ValidationError

from crimescene.scenario.chapter_progress import (
    ChapterUnlockRule,
    advance_chapter,
    next_chapter_choices,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GamePhase, GameState


def make_state(
    *,
    version="case001_1120",
    chapter="CH01",
    unlocked=("CH00", "CH01"),
    stages=None,
):
    state = create_initial_state(
        "issue165-chapter",
        content_version=version,
    )

    return GameState.model_validate({
        **state.model_dump(),
        "phase": GamePhase.INVESTIGATION,
        "current_chapter": chapter,
        "unlocked_chapters": list(unlocked),
        "flags": ["TEST_CHAPTER_APPROVED"],
        "npc_stages": stages or {},
    })


def rule(chapter):
    return ChapterUnlockRule(
        target_chapter=chapter,
        required_flags=frozenset({
            "TEST_CHAPTER_APPROVED",
        }),
    )


def test_legacy_save_default_version():
    state = create_initial_state("legacy-test")
    payload = state.model_dump()

    del payload["content_version"]
    del payload["npc_stages"]

    restored = GameState.model_validate(payload)

    assert restored.content_version == "case001_v7_1"
    assert restored.npc_stages == {}


def test_latest_chapter_choices():
    state = make_state()

    assert next_chapter_choices(state) == (
        "CH02",
        "CH03",
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("CH02", "CH03"),
        ("CH03", "CH02"),
    ],
)
def test_both_investigation_orders(first, second):
    initial = make_state()

    first_state = advance_chapter(
        initial,
        rule=rule(first),
    )

    assert first_state.current_chapter == first
    assert next_chapter_choices(first_state) == (second,)

    second_state = advance_chapter(
        first_state,
        rule=rule(second),
    )

    assert second_state.current_chapter == second
    assert next_chapter_choices(second_state) == ("CH04",)

    final = advance_chapter(
        second_state,
        rule=rule("CH04"),
    )

    assert final.current_chapter == "CH04"
    assert len(final.unlocked_chapters) == 5
    assert final.revision == initial.revision + 3


def test_chapter_four_cannot_be_skipped_to():
    state = make_state()

    with pytest.raises(PermissionError):
        advance_chapter(state, rule=rule("CH04"))


def test_chapter_requires_server_condition():
    state = make_state().model_copy(
        update={"flags": []}
    )

    with pytest.raises(PermissionError):
        advance_chapter(state, rule=rule("CH02"))


def test_legacy_chapter_order_preserved():
    state = make_state(version="case001_v7_1")

    assert next_chapter_choices(state) == ("CH02",)

    with pytest.raises(PermissionError):
        advance_chapter(state, rule=rule("CH03"))


def test_invalid_expanded_chapter_history():
    with pytest.raises(ValidationError):
        make_state(
            chapter="CH04",
            unlocked=("CH00", "CH01", "CH04"),
        )


@pytest.mark.parametrize(
    "stages",
    [
        {"C01": 0},
        {"C01": 4},
        {"C99": 1},
        {"C02": 2},
    ],
)
def test_invalid_npc_stages_rejected(stages):
    with pytest.raises(ValidationError):
        make_state(stages=stages)


def make_stage_policy():
    return AccessPolicy(
        required_evidence=[],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character="C01",
        required_npc_stage=3,
    )


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        (1, False),
        (2, False),
        (3, True),
    ],
)
def test_npc_stage_access_gate(stage, expected):
    state = make_state(
        stages={"C01": stage}
    )

    evaluator = PolicyEvaluator({
        "POL-STAGE": make_stage_policy(),
    })

    assert evaluator.is_allowed(
        "POL-STAGE",
        state,
        active_character_id="C01",
    ) is expected


def test_npc_stage_default_is_one():
    state = make_state()

    evaluator = PolicyEvaluator({
        "POL-STAGE": make_stage_policy(),
    })

    assert not evaluator.is_allowed(
        "POL-STAGE",
        state,
        active_character_id="C01",
    )


def test_stage_policy_cannot_cross_npc_boundary():
    state = make_state(stages={"C01": 3})

    evaluator = PolicyEvaluator({
        "POL-STAGE": make_stage_policy(),
    })

    assert not evaluator.is_allowed(
        "POL-STAGE",
        state,
        active_character_id="C02",
    )
