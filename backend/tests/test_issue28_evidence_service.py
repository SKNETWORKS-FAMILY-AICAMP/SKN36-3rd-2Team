import pytest

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
from crimescene.scenario.schemas.game_state import GamePhase
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
