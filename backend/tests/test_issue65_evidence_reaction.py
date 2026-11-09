"""Regression coverage for collection vs. presentation authorization."""

from types import SimpleNamespace

import pytest

from crimescene.trigger.evidence_reaction import resolve_evidence_reaction

RULES = {"E01": SimpleNamespace(name="일정 수첩")}
RECIPIENTS = {"E01": frozenset({"C02"})}


def test_authorized_presentation_can_set_trigger():
    question, evidence_id = resolve_evidence_reaction(
        "이 증거에 대해 설명해 주세요.",
        "E01",
        active_npc="C02",
        rules=RULES,
        authorized_recipients=RECIPIENTS,
    )
    assert evidence_id == "E01"
    assert "일정 수첩" in question


def test_any_other_unlocked_npc_can_react_without_trigger():
    question, evidence_id = resolve_evidence_reaction(
        "이 증거에 대해 설명해 주세요.",
        "E01",
        active_npc="C01",
        rules=RULES,
        authorized_recipients=RECIPIENTS,
    )
    assert evidence_id is None
    assert "일정 수첩" in question
    assert "설명해 주세요" in question


def test_no_explicit_presentation_rule_falls_back_to_normal_rag():
    question, evidence_id = resolve_evidence_reaction(
        "어떻게 생각하세요?",
        "E01",
        active_npc="C01",
        rules=RULES,
        authorized_recipients={},
    )
    assert evidence_id is None
    assert "일정 수첩" in question


def test_nonexistent_evidence_is_rejected():
    with pytest.raises(ValueError, match="등록되지 않은"):
        resolve_evidence_reaction(
            "보여드립니다",
            "E10",
            active_npc="C01",
            rules=RULES,
            authorized_recipients=RECIPIENTS,
        )


def test_no_evidence_preserves_normal_chat():
    assert resolve_evidence_reaction(
        "안녕하세요",
        None,
        active_npc="C01",
        rules=RULES,
        authorized_recipients=RECIPIENTS,
    ) == ("안녕하세요", None)


def test_long_question_is_clamped_without_leaking_rules():
    question, evidence_id = resolve_evidence_reaction(
        "테스트" * 2000,
        "E01",
        active_npc="C01",
        rules=RULES,
        authorized_recipients=RECIPIENTS,
        max_length=100,
    )
    assert evidence_id is None
    assert len(question) == 100
    assert "일정 수첩" in question
