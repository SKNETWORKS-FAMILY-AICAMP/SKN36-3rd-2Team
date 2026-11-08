"""Issue #24 - NPC 트리거 감지 및 접근 정책 테스트."""

import pytest
from pydantic import ValidationError

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.trigger.npc_trigger import NPCTriggerRule, apply_npc_triggers


def make_state(
    *,
    unlocked=True,
    collected=False,
    presented=False,
    flags=(),
):
    return GameState(
        case_id="CASE-001",
        session_id="TEST-SESSION",
        unlocked_characters=["C01"] if unlocked else [],
        evidence=({"E05": EvidenceState(stage="found")} if collected else {}),
        flags=list(flags),
        presented={"C01": ["E05"]} if presented else {},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


def make_policy(
    *,
    evidence=(),
    presentations=(),
    flags=(),
    topics=("audit",),
):
    return AccessPolicy(
        required_evidence=list(evidence),
        required_presentations=list(presentations),
        required_flags=list(flags),
        required_ending=None,
        required_topics=list(topics),
        required_disclosed_cards=[],
        required_character="C01",
    )


def make_rule(
    *,
    rule_id="TRG-AUDIT",
    policy_id="POL-AUDIT",
    flags=("AUDIT_ASKED",),
    character="C01",
    topic="audit",
):
    return NPCTriggerRule(
        trigger_id=rule_id,
        character_id=character,
        policy_id=policy_id,
        topic=topic,
        phrases=("감사 자료", "장부"),
        grant_flags=flags,
    )


def run(
    question="감사 자료를 확인했나요?",
    *,
    state=None,
    rules=None,
    policies=None,
):
    return apply_npc_triggers(
        question,
        state=make_state() if state is None else state,
        active_character_id="C01",
        rules=[make_rule()] if rules is None else rules,
        evaluator=PolicyEvaluator(
            {"POL-AUDIT": make_policy()} if policies is None else policies
        ),
    )


def test_matched_rule_adds_flag_and_revision_without_mutating_source():
    original = make_state()

    result = run(state=original)

    assert result.trigger_ids == ("TRG-AUDIT",)
    assert result.matched_topics == ("audit",)

    assert result.state.flags == ["AUDIT_ASKED"]
    assert result.state.revision == 1

    assert original.flags == []
    assert original.revision == 0


def test_keyword_matching_normalizes_whitespace():
    result = run("감사   자료는?")

    assert result.trigger_ids == ("TRG-AUDIT",)


def test_unrelated_query_keeps_state_unchanged():
    state = make_state()

    result = run("안녕하세요", state=state)

    assert result.trigger_ids == ()
    assert result.matched_topics == ()
    assert result.state is state


def test_locked_npc_cannot_trigger():
    result = run(state=make_state(unlocked=False))

    assert result.trigger_ids == ()


def test_other_npc_trigger_not_matched():
    result = run(rules=[make_rule(character="C02")])

    assert result.trigger_ids == ()


def test_unknown_policy_fails_closed():
    result = run(rules=[make_rule(policy_id="POL-NOT-FOUND")])

    assert result.trigger_ids == ()


def test_missing_evidence_denied():
    policies = {"POL-AUDIT": make_policy(evidence=("E05",))}

    assert run(policies=policies).trigger_ids == ()

    assert run(
        state=make_state(collected=True),
        policies=policies,
    ).trigger_ids == ("TRG-AUDIT",)


def test_uncollected_evidence_cannot_be_forged_as_presented():
    policies = {"POL-AUDIT": make_policy(presentations=("C01:E05",))}

    result = run(
        state=make_state(presented=True),
        policies=policies,
    )

    assert result.trigger_ids == ()


def test_evidence_presentation_required():
    policies = {"POL-AUDIT": make_policy(presentations=("C01:E05",))}

    result = run(
        state=make_state(collected=True),
        policies=policies,
    )

    assert result.trigger_ids == ()

    state = make_state(
        collected=True,
        presented=True,
    )

    result = run(
        state=state,
        policies=policies,
    )

    assert result.trigger_ids == ("TRG-AUDIT",)


def test_existing_flag_is_idempotent():
    state = make_state(flags=("AUDIT_ASKED",))

    result = run(state=state)

    assert result.state is state
    assert result.state.revision == 0
    assert result.trigger_ids == ("TRG-AUDIT",)


def test_single_question_cannot_chain_new_flags_into_later_policy():
    first = make_rule(
        rule_id="TRG-FIRST",
        flags=("GOT_FLAG",),
    )

    second = make_rule(
        rule_id="TRG-SECOND",
        policy_id="POL-SECOND",
        flags=("SECRET",),
        topic="secret",
    )

    policies = {
        "POL-AUDIT": make_policy(),
        "POL-SECOND": make_policy(
            flags=("GOT_FLAG",),
            topics=("secret",),
        ),
    }

    result = run(
        rules=[first, second],
        policies=policies,
    )

    assert result.trigger_ids == ("TRG-FIRST",)
    assert result.state.flags == ["GOT_FLAG"]


def test_duplicate_trigger_ids_are_rejected():
    with pytest.raises(
        ValueError,
        match="중복",
    ):
        run(
            rules=[
                make_rule(),
                make_rule(),
            ]
        )


def test_invalid_rule_fails_validation():
    with pytest.raises(ValidationError):
        make_rule(rule_id="BAD-ID")

    with pytest.raises(ValidationError):
        NPCTriggerRule(
            trigger_id="TRG-EMPTY",
            character_id="C01",
            policy_id="POL-AUDIT",
            topic="audit",
            phrases=(" ",),
        )


def test_invalid_input_type_is_rejected():
    with pytest.raises(TypeError):
        apply_npc_triggers(
            123,
            state=make_state(),
            active_character_id="C01",
            rules=[],
            evaluator=PolicyEvaluator({}),
        )
