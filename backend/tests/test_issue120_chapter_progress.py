"""Issue #120 - 플레이어 챕터 진행 상태 및 이벤트 접근 검증."""

import pytest
from pydantic import ValidationError

from crimescene.api.django_content_client import ApprovedStoryEvent
from crimescene.api.story_event_gate import select_releasable_story_event
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)


def make_state(**changes):
    data = create_initial_state("chapter-test").model_dump()
    data.update(changes)
    return GameState.model_validate(data)


def make_event(chapter="CH01"):
    return ApprovedStoryEvent(
        event_key=f"EVT-{chapter}-001",
        chapter=chapter,
        trigger_type="EVIDENCE_COLLECTED",
        required_evidence_ids=["E01"],
        title="새로운 기록",
        text="숨겨진 사건이 드러납니다.",
    )


def test_initial_chapter_is_ch00():
    state = create_initial_state("test-session")

    assert state.current_chapter == "CH00"
    assert state.unlocked_chapters == ["CH00"]


def test_legacy_state_remains_compatible():
    data = create_initial_state("legacy-session").model_dump()
    data.pop("current_chapter", None)
    data.pop("unlocked_chapters", None)

    restored = GameState.model_validate(data)

    assert restored.current_chapter == "CH00"
    assert restored.unlocked_chapters == ["CH00"]


def test_locked_chapter_cannot_be_current():
    with pytest.raises(ValidationError):
        make_state(
            phase=GamePhase.INVESTIGATION,
            current_chapter="CH01",
            unlocked_chapters=["CH00"],
        )


def test_duplicate_unlocked_chapter_rejected():
    with pytest.raises(ValidationError):
        make_state(
            unlocked_chapters=["CH00", "CH00"],
        )


def test_initial_chapter_cannot_be_removed():
    with pytest.raises(ValidationError):
        make_state(unlocked_chapters=["CH01"])


def test_unknown_chapter_rejected():
    with pytest.raises(ValidationError):
        make_state(unlocked_chapters=["CH00", "CH05"])


def test_prologue_cannot_start_in_ch01():
    with pytest.raises(ValidationError):
        make_state(
            phase=GamePhase.PROLOGUE,
            current_chapter="CH01",
            unlocked_chapters=["CH00", "CH01"],
        )


def test_inactive_chapter_event_is_blocked():
    state = make_state(
        phase=GamePhase.INVESTIGATION,
        current_chapter="CH00",
        unlocked_chapters=["CH00", "CH01"],
        evidence={"E01": EvidenceState(stage="found")},
    )

    assert select_releasable_story_event(make_event("CH01"), state) is None


def test_active_unlocked_chapter_event_is_allowed():
    state = make_state(
        phase=GamePhase.INVESTIGATION,
        current_chapter="CH01",
        unlocked_chapters=["CH00", "CH01"],
        evidence={"E01": EvidenceState(stage="found")},
    )

    event = make_event("CH01")

    assert select_releasable_story_event(event, state) == event
