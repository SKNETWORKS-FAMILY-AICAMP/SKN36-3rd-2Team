"""Issue #63: 실제 증거 획득 정책 구성의 fail-closed 검증."""

import json

import pytest

from crimescene.api.chat_bootstrap import _load_acquisition_policies
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule


def make_inputs(*, card_requirements=None, holder="C01"):
    rules = {
        "E01": EvidenceRule(
            name="증거",
            score=2,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
    }
    policies = {
        "POL-ACQUIRE-E01": AccessPolicy(
            required_character=holder,
            required_evidence=[],
            required_presentations=[],
            required_flags=[],
            required_ending=None,
            required_topics=[],
            required_disclosed_cards=(
                ["KC01-E01"] if card_requirements is None else card_requirements
            ),
        )
    }
    cards = [{"id": "KC01-E01", "character_id": "C01"}]
    return rules, policies, cards


def load(path, *, rules, policies, cards):
    return _load_acquisition_policies(
        path,
        evidence_rules=rules,
        policies=policies,
        npc_cards=cards,
    )


def test_missing_acquisition_file_defaults_to_deny():
    rules, policies, cards = make_inputs()
    assert load(None, rules=rules, policies=policies, cards=cards) == {}


def test_valid_policy_mapping(tmp_path):
    rules, policies, cards = make_inputs()
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"E01": "POL-ACQUIRE-E01"}), encoding="utf-8")
    assert load(path, rules=rules, policies=policies, cards=cards) == {
        "E01": "POL-ACQUIRE-E01"
    }


def test_policy_without_disclosed_card_rejected(tmp_path):
    rules, policies, cards = make_inputs(card_requirements=[])
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"E01": "POL-ACQUIRE-E01"}), encoding="utf-8")
    with pytest.raises(ValueError, match="공개 지식 카드"):
        load(path, rules=rules, policies=policies, cards=cards)


def test_policy_with_wrong_npc_rejected(tmp_path):
    rules, policies, cards = make_inputs(holder="C02")
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"E01": "POL-ACQUIRE-E01"}), encoding="utf-8")
    with pytest.raises(ValueError, match="보유 NPC"):
        load(path, rules=rules, policies=policies, cards=cards)


def test_unregistered_card_rejected(tmp_path):
    rules, policies, cards = make_inputs(card_requirements=["FORGED-CARD"])
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"E01": "POL-ACQUIRE-E01"}), encoding="utf-8")
    with pytest.raises(ValueError, match="지식 카드"):
        load(path, rules=rules, policies=policies, cards=cards)
