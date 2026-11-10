"""Issue #33: CASE-001 게임 진행 규칙 회귀 테스트.

실제 Ollama E2E와 구분되는 결정론적 엔진 테스트입니다.
비공개 원장과 외부 서비스는 사용하지 않습니다.
"""

import pytest

from crimescene.scenario.accusation import can_accuse
from crimescene.scenario.evidence_collection import collect_evidence
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.npc_unlock import NPCUnlockRule, find_unlockable_npcs
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)

# 실제 플레이 검증에서 확인된 증거 순서 및 획득 조건
SCENARIO = {
    "E01": ("C01", 1, (), ()),
    "E02": ("C05", 2, ("E10",), ()),
    "E03": ("C06", 3, ("E02",), ("C06:E02",)),
    "E04": ("C04", 2, ("E01",), ("C04:E01",)),
    "E05": ("C03", 3, ("E04",), ()),
    "E06": (
        "C04", 3, ("E03", "E04", "E05"),
        ("C04:E04", "C04:E05"),
    ),
    "E07": ("C08", 2, ("E03", "E04"), ("C08:E04",)),
    "E08": ("C09", 2, ("E04",), ()),
    "E09": ("C03", 1, ("E04",), ()),
    "E10": ("C05", 2, ("E01",), ()),
}

FIND_CARDS = {
    "E01": "K-C01-03",
    "E02": "K-C05-03",
    "E03": "K-C06-04",
    "E04": "K-C04-03",
    "E05": "K-C03-03",
    "E06": "K-C04-07",
    "E07": "K-C08-04",
    "E08": "K-C09-04",
    "E09": "K-C03-04",
    "E10": "K-C05-02",
}

ORDER = (
    "E01", "E04", "E05", "E10", "E09",
    "E02", "E03", "E06", "E07", "E08",
)

UNLOCK_RULES = {
    npc: NPCUnlockRule(required_evidence=frozenset(required))
    for npc, required in {
        "C02": ("E01",),
        "C03": ("E04",),
        "C04": ("E01",),
        "C05": ("E01",),
        "C06": ("E02",),
        "C07": ("E02",),
        "C08": ("E03",),
        "C09": ("E10",),
        "C10": ("E03",),
    }.items()
}


@pytest.fixture
def setup():
    rules = {}
    policies = {}
    policy_ids = {}

    for evidence_id, (holder, score, prerequisites, presentations) in SCENARIO.items():
        rules[evidence_id] = EvidenceRule(
            name=f"Test {evidence_id}",
            score=score,
            holder=holder,
            prerequisites=list(prerequisites),
            presentation=list(presentations),
            q=[],
        )

        policy_id = f"TEST-ACQUIRE-{evidence_id}"
        policy_ids[evidence_id] = policy_id

        # 대화에서 실제 공개된 카드를 요구하는 수집 정책
        policies[policy_id] = AccessPolicy(
            required_character=holder,
            required_evidence=list(prerequisites),
            required_presentations=list(presentations),
            required_disclosed_cards=[FIND_CARDS[evidence_id]],
            required_topics=[],
            required_flags=[],
            required_ending=None,
        )

    return rules, policy_ids, PolicyEvaluator(policies)


def investigation_state(session_id):
    return transition_phase(
        create_initial_state(session_id),
        GamePhase.INVESTIGATION,
    )


def test_all_evidence_and_npc_unlock_sequence(setup):
    rules, policy_ids, evaluator = setup
    state = investigation_state("issue33-flow")

    assert len(rules) == 10
    assert sum(rule.score for rule in rules.values()) == 21

    expected_scores = (1, 3, 6, 8, 9, 11, 14, 17, 19, 21)

    for evidence_id, expected_score in zip(ORDER, expected_scores):
        holder, _, _, presentations = SCENARIO[evidence_id]
        card_id = FIND_CARDS[evidence_id]

        assert holder in state.unlocked_characters

        # 발견 카드 미공개 상태에서는 수집 불가
        assert not evaluator.is_allowed(
            policy_ids[evidence_id],
            state,
            active_character_id=holder,
        )

        # 승인된 NPC 대화가 카드 공개 및 증거 제시를
        # 완료한 상황을 엔진 테스트용으로 구성
        presented = {
            npc: list(ids)
            for npc, ids in state.presented.items()
        }

        for presentation in presentations:
            npc, presented_id = presentation.split(":")
            presented.setdefault(npc, [])
            if presented_id not in presented[npc]:
                presented[npc].append(presented_id)

        state = GameState.model_validate({
            **state.model_dump(),
            "disclosed_cards": [*state.disclosed_cards, card_id],
            "presented": presented,
        })

        result = collect_evidence(
            state=state,
            evidence_id=evidence_id,
            evidence_rules=rules,
            acquisition_policy_ids=policy_ids,
            evaluator=evaluator,
            active_character_id=holder,
        )

        assert result.created is True
        assert result.state.score == expected_score

        unlocked = find_unlockable_npcs(
            result.state,
            UNLOCK_RULES,
        )

        state = GameState.model_validate({
            **result.state.model_dump(),
            "unlocked_characters": [
                *result.state.unlocked_characters,
                *unlocked,
            ],
        })

        if expected_score < 11:
            assert can_accuse(state, rules) is False
        else:
            assert can_accuse(state, rules) is True

    assert set(state.evidence) == set(SCENARIO)
    assert set(state.unlocked_characters) == {
        f"C{i:02d}" for i in range(1, 11)
    }
    assert state.score == 21


def test_e06_requires_both_evidence_presentations(setup):
    rules, policy_ids, evaluator = setup

    state = investigation_state("issue33-e06")
    state = GameState.model_validate({
        **state.model_dump(),
        "unlocked_characters": ["C01", "C04"],
        "evidence": {
            eid: EvidenceState(stage="found").model_dump()
            for eid in ("E03", "E04", "E05")
        },
        "score": 8,
        "disclosed_cards": ["K-C04-07"],
        "presented": {"C04": ["E04"]},
    })

    # E04만 제시한 상태에서는 E06 수집 차단
    with pytest.raises(PermissionError):
        collect_evidence(
            state=state,
            evidence_id="E06",
            evidence_rules=rules,
            acquisition_policy_ids=policy_ids,
            evaluator=evaluator,
            active_character_id="C04",
        )

    state = GameState.model_validate({
        **state.model_dump(),
        "presented": {"C04": ["E04", "E05"]},
    })

    result = collect_evidence(
        state=state,
        evidence_id="E06",
        evidence_rules=rules,
        acquisition_policy_ids=policy_ids,
        evaluator=evaluator,
        active_character_id="C04",
    )

    assert result.created is True
    assert result.state.score == 11
    assert "E06" in result.state.evidence


def test_accusation_requires_evidence_and_score(setup):
    rules, _, _ = setup

    state = investigation_state("issue33-threshold")

    # 증거 5개지만 9점: 지목 불가
    five = ("E01", "E04", "E05", "E09", "E10")
    state = GameState.model_validate({
        **state.model_dump(),
        "evidence": {
            eid: EvidenceState(stage="found").model_dump()
            for eid in five
        },
        "score": 9,
    })

    assert can_accuse(state, rules) is False

    # E02까지 획득해 11점: 지목 가능
    state = GameState.model_validate({
        **state.model_dump(),
        "evidence": {
            **{
                eid: evidence.model_dump()
                for eid, evidence in state.evidence.items()
            },
            "E02": EvidenceState(stage="found").model_dump(),
        },
        "score": 11,
    })

    assert can_accuse(state, rules) is True
