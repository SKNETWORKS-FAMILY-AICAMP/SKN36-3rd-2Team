
"""Issue #145 - Story Context 읽기 전용 및 접근 경계 테스트."""

from dataclasses import FrozenInstanceError

import pytest

from crimescene.agents.contracts import AgentContext
from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
    ContentServiceNotFoundError,
)
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)
from crimescene.scenario.story_context import StoryContextService
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def state():
    return GameState(
        case_id="CASE-001",
        session_id="TEST-STORY-CONTEXT",
        phase=GamePhase.INVESTIGATION,
        current_chapter="CH01",
        unlocked_chapters=["CH00", "CH01"],
        unlocked_characters=["C01", "C02"],
        evidence={
            "E01": EvidenceState(stage="found"),
            "E02": EvidenceState(stage="resolved"),
            "E03": EvidenceState(stage="hidden"),
        },
        presented={
            "C01": ["E01", "E03"],
            "C02": ["E02"],
            "C03": ["E01"],
        },
        flags=["FLAG-TEST"],
        disclosed_cards=["K-C01-01"],
        document_grants=[],
        attempts_left=3,
        score=0,
        outcome=None,
        deep_eligible=False,
        revision=5,
                queued_story_events=[
            "STORY_001",
            "STORY_002",
            "STORY_003",
            "STORY_004",
            "STORY_005",
        ],
        acknowledged_story_events=["STORY_002"],
    )


@pytest.fixture
def repository(tmp_path, state):
    repo = SQLiteCase001Repository(
        tmp_path / "story-context.sqlite3"
    )

    repo.save_selection(
        state.session_id,
        "C01",
        state.revision,
    )
    repo.register_state(state)

    return repo


@pytest.fixture
def context(repository, state):
    service = StoryContextService(repository)

    return service.load(
        state.session_id,
        expected_revision=state.revision,
    )


def test_story_context_uses_current_progress(context, state):
    assert context.case_id == state.case_id
    assert context.session_id == state.session_id
    assert context.revision == 5
    assert context.phase == GamePhase.INVESTIGATION
    assert context.current_chapter == "CH01"
    assert context.can_investigate is True


def test_only_unlocked_chapters_are_included(context):
    assert context.unlocked_chapters == ("CH00", "CH01")
    assert "CH02" not in context.unlocked_chapters
    assert "CH03" not in context.unlocked_chapters
    assert "CH04" not in context.unlocked_chapters


def test_only_collected_evidence_is_included(context):
    assert context.collected_evidence_ids == ("E01", "E02")
    assert "E03" not in context.collected_evidence_ids


def test_presented_evidence_is_separated_by_npc(context):
    assert context.get_presented_evidence("C01") == ("E01",)
    assert context.get_presented_evidence("C02") == ("E02",)


def test_locked_npc_presentation_is_excluded(context):
    assert "C03" not in context.unlocked_characters
    assert context.get_presented_evidence("C03") == ()


def test_only_disclosed_card_ids_are_included(context):
    assert context.disclosed_card_ids == ("K-C01-01",)
    assert "K-C02-PRIVATE" not in context.disclosed_card_ids


def test_context_is_immutable(context):
    with pytest.raises(FrozenInstanceError):
        context.revision = 100


def test_read_does_not_change_sqlite_state(
    repository,
    state,
):
    before = repository.load_state(state.session_id)

    service = StoryContextService(repository)
    service.load(
        state.session_id,
        expected_revision=state.revision,
    )

    after = repository.load_state(state.session_id)

    assert before == after
    assert after.revision == state.revision


@pytest.mark.parametrize("revision", [0, 4, 6, 100])
def test_revision_mismatch_is_rejected(
    repository,
    state,
    revision,
):
    service = StoryContextService(repository)

    with pytest.raises(ValueError, match="revision"):
        service.load(
            state.session_id,
            expected_revision=revision,
        )


def test_unknown_session_is_rejected(repository):
    service = StoryContextService(repository)

    with pytest.raises(ValueError):
        service.load(
            "UNKNOWN-SESSION",
            expected_revision=0,
        )


@pytest.fixture
def event_bindings():
    return {
        "EVT-CH01-001": StoryEventBinding(
            "STORY_001", "EVT-CH01-001", "CH01"
        ),
        "EVT-CH01-002": StoryEventBinding(
            "STORY_002", "EVT-CH01-002", "CH01"
        ),
        "EVT-CH02-003": StoryEventBinding(
            "STORY_003", "EVT-CH02-003", "CH02"
        ),
        "EVT-CH01-004": StoryEventBinding(
            "STORY_004", "EVT-CH01-004", "CH01"
        ),
        "EVT-CH01-005": StoryEventBinding(
            "STORY_005", "EVT-CH01-005", "CH01"
        ),
        "EVT-CH01-006": StoryEventBinding(
            "STORY_006", "EVT-CH01-006", "CH01"
        ),
    }


def make_approved_event(
    event_key,
    *,
    evidence_id="E01",
):
    return ApprovedStoryEvent(
        event_key=event_key,
        chapter="CH01",
        trigger_type="EVIDENCE_COLLECTED",
        required_evidence_ids=[evidence_id],
        title="테스트 이벤트",
        text="테스트 스토리입니다.",
    )


def test_only_authorized_pending_events_are_returned(
    repository,
    state,
    event_bindings,
):
    calls = []

    def fetch(event_key):
        calls.append(event_key)

        if event_key == "EVT-CH01-005":
            raise ContentServiceNotFoundError("Not approved")

        evidence_id = (
            "E03" if event_key == "EVT-CH01-004" else "E01"
        )

        return make_approved_event(
            event_key,
            evidence_id=evidence_id,
        )

    before = repository.load_state(state.session_id)

    service = StoryContextService(repository)

    result = service.load_pending_event_keys(
        state.session_id,
        expected_revision=state.revision,
        bindings=event_bindings,
        fetch_approved_event=fetch,
    )

    assert result == ("EVT-CH01-001",)

    assert calls == [
        "EVT-CH01-001",
        "EVT-CH01-004",
        "EVT-CH01-005",
    ]

    assert repository.load_state(state.session_id) == before


def test_event_service_failure_does_not_return_partial_results(
    repository,
    state,
    event_bindings,
):
    def fetch(event_key):
        if event_key == "EVT-CH01-004":
            raise ContentServiceError("Django unavailable")

        return make_approved_event(event_key)

    service = StoryContextService(repository)

    with pytest.raises(ContentServiceError):
        service.load_pending_event_keys(
            state.session_id,
            expected_revision=state.revision,
            bindings=event_bindings,
            fetch_approved_event=fetch,
        )

    assert repository.load_state(state.session_id) == state


def test_invalid_event_binding_is_rejected(
    repository,
    state,
):
    service = StoryContextService(repository)

    bindings = {
        "EVT-CH01-999": StoryEventBinding(
            "STORY_001",
            "EVT-CH01-001",
            "CH01",
        ),
    }

    with pytest.raises(ValueError):
        service.load_pending_event_keys(
            state.session_id,
            expected_revision=state.revision,
            bindings=bindings,
            fetch_approved_event=make_approved_event,
        )


def test_empty_event_bindings_return_empty_result(
    repository,
    state,
):
    service = StoryContextService(repository)

    result = service.load_pending_event_keys(
        state.session_id,
        expected_revision=state.revision,
        bindings={},
        fetch_approved_event=make_approved_event,
    )

    assert result == ()


def test_story_context_matches_agent_context(
    repository,
    state,
):
    # Compare shared fields between the two context contracts.
    story = StoryContextService(repository).load(
        state.session_id,
        expected_revision=state.revision,
    )

    agent = AgentContext.from_game_state(
        state,
        active_character_id="C01",
    )

    assert story.session_id == agent.session_id
    assert story.case_id == agent.case_id
    assert story.revision == agent.revision
    assert story.phase == agent.phase
    assert story.current_chapter == agent.current_chapter
    assert story.unlocked_characters == agent.unlocked_characters

    # Story Context excludes uncollected evidence.
    assert story.collected_evidence_ids == ("E01", "E02")
    assert set(story.collected_evidence_ids).issubset(
        agent.collected_evidence_ids
    )


def test_context_refresh_after_state_update(repository, state):
    service = StoryContextService(repository)

    before = service.load(
        state.session_id,
        expected_revision=state.revision,
    )

    updated = GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            "revision": state.revision + 1,
            "evidence": {
                **state.evidence,
                "E03": EvidenceState(stage="found"),
            },
        }
    )

    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    after = service.load(
        state.session_id,
        expected_revision=updated.revision,
    )

    assert before.collected_evidence_ids == ("E01", "E02")
    assert after.collected_evidence_ids == ("E01", "E02", "E03")
    assert before.revision == state.revision
    assert after.revision == updated.revision


def test_revision_change_during_event_fetch_is_rejected(
    repository,
    state,
    event_bindings,
):
    service = StoryContextService(repository)

    def fetch(event_key):
        if event_key == "EVT-CH01-001":
            updated = GameState.model_validate(
                {
                    **state.model_dump(mode="python"),
                    "revision": state.revision + 1,
                    "flags": [*state.flags, "FLAG-CONCURRENT"],
                }
            )

            repository.commit_state(
                expected_state=state,
                updated_state=updated,
            )

        return make_approved_event(event_key)

    with pytest.raises(ValueError, match="revision"):
        service.load_pending_event_keys(
            state.session_id,
            expected_revision=state.revision,
            bindings=event_bindings,
            fetch_approved_event=fetch,
        )


@pytest.mark.parametrize(
    "phase",
    [GamePhase.ACCUSATION, GamePhase.FINISHED],
)
def test_non_investigation_phase_blocks_pending_events(
    tmp_path,
    state,
    event_bindings,
    phase,
):
    updated = GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            "phase": phase,
            "outcome": "SUCCESS" if phase == GamePhase.FINISHED else None,
        }
    )

    repo = SQLiteCase001Repository(
        tmp_path / "blocked-context.sqlite3"
    )
    repo.save_selection(
        updated.session_id,
        "C01",
        updated.revision,
    )
    repo.register_state(updated)

    service = StoryContextService(repo)

    def fetch(event_key):
        pytest.fail("Django must not be called outside investigation")

    result = service.load_pending_event_keys(
        updated.session_id,
        expected_revision=updated.revision,
        bindings=event_bindings,
        fetch_approved_event=fetch,
    )

    assert result == ()
    assert repo.load_state(updated.session_id) == updated
