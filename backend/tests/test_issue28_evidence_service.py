import pytest

from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
)
from crimescene.api.story_event_conditions import StoryEventConditions
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.api.story_event_progress import stage_story_events
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.scenario.evidence_service import collect_evidence_atomic
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.npc_unlock import NPCUnlockRule
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def make_rules():
    return {
        "E01": EvidenceRule(
            name="첫 번째 증거",
            score=2,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
    }


def make_evaluator():
    return PolicyEvaluator(
        {
            "POL-COLLECT": AccessPolicy(
                required_evidence=[],
                required_presentations=[],
                required_flags=[],
                required_ending=None,
                required_topics=[],
                required_disclosed_cards=[],
                required_character="C01",
            )
        }
    )


def setup_game(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")

    state = create_initial_state("test-session")

    store = NPCSessionStore(repository=repository)
    store.select_npc(state, "C01")
    repository.register_state(state)

    updated = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    return repository


def collect(repository, **kwargs):
    return collect_evidence_atomic(
        session_id="test-session",
        evidence_id="E01",
        active_character_id=kwargs.get("npc", "C01"),
        repository=repository,
        evidence_rules=kwargs.get("rules", make_rules()),
        acquisition_policy_ids={"E01": "POL-COLLECT"},
        evaluator=make_evaluator(),
        unlock_rules=kwargs.get(
            "unlocks",
            {"C02": NPCUnlockRule(required_evidence=frozenset({"E01"}))},
        ),
        stage_events=kwargs.get("stage_events"),
    )


def test_collect_and_unlock_atomic(tmp_path):
    repository = setup_game(tmp_path)

    result = collect(repository)

    saved = repository.load_state("test-session")

    assert result.created is True
    assert result.unlocked_npcs == ("C02",)

    assert saved.evidence["E01"].stage == "found"
    assert saved.score == 2
    assert saved.unlocked_characters == ["C01", "C02"]

    # 조사 단계 전환 + 증거 획득
    assert saved.revision == 2

    # NPC 세션도 같은 revision을 사용해야 합니다.
    assert repository.load_selection("test-session") == ("C01", 2)


def test_duplicate_collection_is_idempotent(tmp_path):
    repository = setup_game(tmp_path)

    first = collect(repository)
    second = collect(repository)

    assert first.created is True
    assert second.created is False

    assert second.unlocked_npcs == ()
    assert second.state.score == 2
    assert second.state.revision == 2


def test_wrong_npc_cannot_collect(tmp_path):
    repository = setup_game(tmp_path)

    before = repository.load_state("test-session")

    with pytest.raises(PermissionError):
        collect(repository, npc="C02")

    after = repository.load_state("test-session")

    assert before == after


def test_wrong_evidence_holder_is_blocked(tmp_path):
    repository = setup_game(tmp_path)

    rules = make_rules()
    rules["E01"] = rules["E01"].model_copy(update={"holder": "C03"})

    with pytest.raises(PermissionError):
        collect(repository, rules=rules)

    assert repository.load_state("test-session").score == 0


def test_failed_unlock_does_not_save_evidence(tmp_path):
    repository = setup_game(tmp_path)

    before = repository.load_state("test-session")

    invalid_rules = {"C99": NPCUnlockRule(required_evidence=frozenset({"E01"}))}

    with pytest.raises(ValueError):
        collect(repository, unlocks=invalid_rules)

    after = repository.load_state("test-session")

    # NPC 해금 판정이 실패하면 증거도 저장되지 않습니다.
    assert before == after
    assert after.evidence == {}
    assert after.score == 0

@pytest.fixture
def event_runtime(tmp_path):
    repository = setup_game(tmp_path)

    current = repository.load_state("test-session")

    ready = GameState.model_validate(
        {
            **current.model_dump(mode="python"),
            "flags": ["TEST_EVENT_READY"],
            "revision": current.revision + 1,
        }
    )

    repository.commit_state(
        expected_state=current,
        updated_state=ready,
    )

    bindings = {
        "EVT-CH00-001": StoryEventBinding(
            source_story_id="STORY_001",
            event_key="EVT-CH00-001",
            chapter="CH00",
        )
    }

    conditions = {
        "STORY_001": StoryEventConditions(
            story_id="STORY_001",
            chapter="CH00",
            all_evidence=frozenset({"E01"}),
            required_flags=frozenset(
                {"TEST_EVENT_READY"}
            ),
        )
    }

    def fetch_approved(event_key):
        return ApprovedStoryEvent(
            event_key=event_key,
            chapter="CH00",
            trigger_type="EVIDENCE_COLLECTED",
            required_evidence_ids=["E01"],
            title="Test event",
            text="Approved test content",
        )

    def stage_events(state):
        return stage_story_events(
            state,
            bindings=bindings,
            conditions=conditions,
            fetch_approved_event=fetch_approved,
        )

    return repository, stage_events


def test_evidence_and_story_event_commit_atomically(
    event_runtime,
):
    repository, stage_events = event_runtime

    before = repository.load_state("test-session")

    result = collect(
        repository,
        stage_events=stage_events,
    )

    saved = repository.load_state("test-session")

    assert result.created is True
    assert saved == result.state
    assert saved.evidence["E01"].stage == "found"
    assert saved.score == 2
    assert "C02" in saved.unlocked_characters
    assert saved.queued_story_events == ["STORY_001"]

    # 증거 수집과 이벤트 큐는 동일한 revision으로 저장됩니다.
    assert saved.revision == before.revision + 1

    assert repository.load_selection("test-session") == (
        "C01",
        saved.revision,
    )


def test_duplicate_collection_does_not_queue_again(
    event_runtime,
):
    repository, stage_events = event_runtime

    first = collect(
        repository,
        stage_events=stage_events,
    )

    def unexpected_stage(state):
        pytest.fail("Duplicate collection evaluated events")

    second = collect(
        repository,
        stage_events=unexpected_stage,
    )

    assert first.created is True
    assert second.created is False
    assert second.state == first.state
    assert second.state.queued_story_events == [
        "STORY_001"
    ]


def test_story_event_failure_rolls_back_collection(
    event_runtime,
):
    repository, _ = event_runtime

    before = repository.load_state("test-session")
    selection = repository.load_selection("test-session")

    def fail_stage(state):
        raise ContentServiceError("Django unavailable")

    with pytest.raises(ContentServiceError):
        collect(
            repository,
            stage_events=fail_stage,
        )

    saved = repository.load_state("test-session")

    assert saved == before
    assert saved.evidence == {}
    assert saved.score == 0
    assert saved.queued_story_events == []
    assert repository.load_selection(
        "test-session"
    ) == selection


def test_story_event_cas_failure_preserves_state(
    event_runtime,
    monkeypatch,
):
    repository, stage_events = event_runtime

    before = repository.load_state("test-session")

    def fail_commit(*, expected_state, updated_state):
        assert updated_state.queued_story_events == [
            "STORY_001"
        ]

        raise ValueError("Stale revision")

    monkeypatch.setattr(
        repository,
        "commit_state",
        fail_commit,
    )

    with pytest.raises(ValueError):
        collect(
            repository,
            stage_events=stage_events,
        )

    assert repository.load_state("test-session") == before
    assert repository.load_selection("test-session") == (
        "C01",
        before.revision,
    )