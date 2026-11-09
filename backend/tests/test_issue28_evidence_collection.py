import pytest

from crimescene.scenario.evidence_collection import (
    collect_evidence,
    get_collection_progress,
)
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase


def make_rules():
    return {
        "E01": EvidenceRule(
            name="첫 번째 증거",
            score=2,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
        "E02": EvidenceRule(
            name="두 번째 증거",
            score=3,
            holder="C01",
            prerequisites=["E01"],
            presentation=[],
            q=[],
        ),
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


def make_state():
    state = create_initial_state("test-session")

    return transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )


def collect(state, evidence_id, **kwargs):
    return collect_evidence(
        state=state,
        evidence_id=evidence_id,
        evidence_rules=kwargs.get("rules", make_rules()),
        acquisition_policy_ids=kwargs.get(
            "policies",
            {
                "E01": "POL-COLLECT",
                "E02": "POL-COLLECT",
            },
        ),
        evaluator=make_evaluator(),
        active_character_id="C01",
    )


def test_collect_evidence():
    result = collect(make_state(), "E01")

    assert result.created is True
    assert result.state.evidence["E01"].stage == "found"
    assert result.state.score == 2
    assert result.progress.total == 5
    assert result.progress.collected_count == 1


def test_duplicate_collection():
    first = collect(make_state(), "E01")
    second = collect(first.state, "E01")

    assert second.created is False
    assert second.state == first.state
    assert second.state.score == 2
    assert second.state.revision == first.state.revision


def test_missing_prerequisite():
    with pytest.raises(PermissionError):
        collect(make_state(), "E02")


def test_prerequisite_satisfied():
    first = collect(make_state(), "E01")
    second = collect(first.state, "E02")

    assert second.state.score == 5
    assert second.progress.collected_count == 2


def test_unknown_evidence():
    with pytest.raises(ValueError):
        collect(make_state(), "E99")


def test_missing_collection_policy():
    with pytest.raises(PermissionError):
        collect(
            make_state(),
            "E01",
            policies={},
        )


def test_collection_blocked_during_prologue():
    with pytest.raises(PermissionError):
        collect(
            create_initial_state("test-session"),
            "E01",
        )


def test_score_integrity():
    state = make_state().model_copy(update={"score": 10})

    # 조회 함수는 수집된 증거를 기준으로 점수를 계산합니다.
    progress = get_collection_progress(state, make_rules())

    assert progress.score == 0

    # 실제 증거 수집 시 저장된 점수와 계산된 점수를 비교합니다.
    with pytest.raises(ValueError):
        collect(state, "E01")
