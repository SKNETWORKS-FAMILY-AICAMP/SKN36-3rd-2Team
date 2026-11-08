"""Issue #24 - 증거 제시와 NPC 트리거 통합 테스트."""

import pytest

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.trigger.evidence_presentation import (
    process_npc_dialogue_event,
    record_evidence_presentation,
)
from crimescene.trigger.npc_trigger import NPCTriggerRule


def make_state(
    *,
    collected=True,
    stage="found",
    unlocked=("C01",),
    presented=None,
) -> GameState:
    evidence = {}

    if collected:
        evidence["E05"] = EvidenceState(stage=stage)

    return GameState(
        case_id="CASE-001",
        session_id="TEST-24-PRESENTATION",
        unlocked_characters=list(unlocked),
        evidence=evidence,
        flags=[],
        presented=presented or {},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


def make_evidence_rules():
    return {
        "E05": EvidenceRule(
            name="테스트 감사 자료",
            score=1,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
    }


def make_recipients():
    return {
        "E05": frozenset({"C01"}),
    }


def make_trigger():
    return NPCTriggerRule(
        trigger_id="TRG-AUDIT-PRESENTED",
        character_id="C01",
        policy_id="POL-AUDIT-PRESENTED",
        topic="audit",
        phrases=("감사 자료", "장부"),
        grant_flags=("AUDIT_DISCLOSED",),
    )


def make_evaluator():
    return PolicyEvaluator(
        {
            "POL-AUDIT-PRESENTED": AccessPolicy(
                required_evidence=["E05"],
                required_presentations=["C01:E05"],
                required_flags=[],
                required_ending=None,
                required_topics=["audit"],
                required_disclosed_cards=[],
                required_character="C01",
            )
        }
    )


def present(
    *,
    state=None,
    npc="C01",
    evidence_id="E05",
    recipients=None,
):
    return record_evidence_presentation(
        state=make_state() if state is None else state,
        active_character_id=npc,
        evidence_id=evidence_id,
        evidence_rules=make_evidence_rules(),
        allowed_recipients=(make_recipients() if recipients is None else recipients),
    )


def test_valid_evidence_presentation():
    original = make_state()

    result = present(state=original)

    assert result.created is True
    assert result.state.presented == {"C01": ["E05"]}
    assert result.state.revision == 1

    # 원본 불변
    assert original.presented == {}
    assert original.revision == 0


def test_uncollected_evidence_is_blocked():
    with pytest.raises(PermissionError):
        present(state=make_state(collected=False))


def test_unavailable_evidence_stage_is_blocked():
    with pytest.raises(PermissionError):
        present(state=make_state(stage="locked"))


def test_resolved_evidence_is_allowed():
    result = present(state=make_state(stage="resolved"))

    assert result.created is True


def test_locked_npc_is_blocked():
    with pytest.raises(PermissionError):
        present(state=make_state(unlocked=()))


def test_unknown_evidence_is_blocked():
    with pytest.raises(ValueError):
        present(evidence_id="E99")


def test_other_npc_cannot_receive_evidence():
    with pytest.raises(PermissionError):
        present(
            state=make_state(unlocked=("C01", "C02")),
            npc="C02",
        )


def test_missing_recipient_rule_is_denied():
    with pytest.raises(PermissionError):
        present(recipients={})


def test_invalid_recipient_rule_is_denied():
    with pytest.raises(PermissionError):
        present(recipients={"E05": ["C01"]})


def test_duplicate_presentation_is_idempotent():
    original = make_state()

    first = present(state=original)
    second = present(state=first.state)

    assert first.created is True
    assert second.created is False

    assert second.state is first.state
    assert second.state.revision == 1
    assert second.state.presented == {"C01": ["E05"]}


def test_other_npc_presentation_is_preserved():
    state = make_state(presented={"C02": ["E03"]})

    result = present(state=state)

    assert result.state.presented == {
        "C02": ["E03"],
        "C01": ["E05"],
    }


def test_question_without_presentation_cannot_unlock_secret():
    result = process_npc_dialogue_event(
        "감사 자료에 대해 알려주세요.",
        state=make_state(),
        active_character_id="C01",
        trigger_rules=[make_trigger()],
        evaluator=make_evaluator(),
        evidence_rules=make_evidence_rules(),
        allowed_recipients=make_recipients(),
    )

    assert result.presentation_created is False
    assert result.trigger_ids == ()
    assert result.state.flags == []
    assert result.state.revision == 0


def test_presentation_unlocks_trigger():
    original = make_state()

    result = process_npc_dialogue_event(
        "감사 자료에 대해 알려주세요.",
        state=original,
        active_character_id="C01",
        trigger_rules=[make_trigger()],
        evaluator=make_evaluator(),
        evidence_rules=make_evidence_rules(),
        allowed_recipients=make_recipients(),
        presented_evidence_id="E05",
    )

    assert result.presentation_created is True
    assert result.trigger_ids == ("TRG-AUDIT-PRESENTED",)
    assert result.matched_topics == ("audit",)

    assert result.state.presented == {"C01": ["E05"]}

    assert result.state.flags == ["AUDIT_DISCLOSED"]

    # 증거 제시와 신규 플래그 생성으로 2회 증가
    assert result.state.revision == 2

    # 원본 GameState는 그대로 유지
    assert original.presented == {}
    assert original.flags == []


def test_presentation_without_keyword_does_not_trigger():
    result = process_npc_dialogue_event(
        "안녕하세요.",
        state=make_state(),
        active_character_id="C01",
        trigger_rules=[make_trigger()],
        evaluator=make_evaluator(),
        evidence_rules=make_evidence_rules(),
        allowed_recipients=make_recipients(),
        presented_evidence_id="E05",
    )

    assert result.presentation_created is True
    assert result.trigger_ids == ()

    assert result.state.presented == {"C01": ["E05"]}

    assert result.state.flags == []
    assert result.state.revision == 1


def test_failed_presentation_cannot_change_state():
    original = make_state(collected=False)

    with pytest.raises(PermissionError):
        process_npc_dialogue_event(
            "감사 자료에 대해 알려주세요.",
            state=original,
            active_character_id="C01",
            trigger_rules=[make_trigger()],
            evaluator=make_evaluator(),
            evidence_rules=make_evidence_rules(),
            allowed_recipients=make_recipients(),
            presented_evidence_id="E05",
        )

    assert original.flags == []
    assert original.presented == {}
    assert original.revision == 0


def test_repeated_dialogue_does_not_duplicate_flags():
    first = process_npc_dialogue_event(
        "감사 자료에 대해 알려주세요.",
        state=make_state(),
        active_character_id="C01",
        trigger_rules=[make_trigger()],
        evaluator=make_evaluator(),
        evidence_rules=make_evidence_rules(),
        allowed_recipients=make_recipients(),
        presented_evidence_id="E05",
    )

    second = process_npc_dialogue_event(
        "감사 자료에 대해 알려주세요.",
        state=first.state,
        active_character_id="C01",
        trigger_rules=[make_trigger()],
        evaluator=make_evaluator(),
        evidence_rules=make_evidence_rules(),
        allowed_recipients=make_recipients(),
        presented_evidence_id="E05",
    )

    assert second.presentation_created is False
    assert second.state.revision == 2
    assert second.state.flags == ["AUDIT_DISCLOSED"]
    assert second.state.presented == {"C01": ["E05"]}
