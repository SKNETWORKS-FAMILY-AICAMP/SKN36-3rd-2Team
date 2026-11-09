"""실제 CASE-001 획득 정책과 위조·선행조건 우회를 검사합니다."""

from pathlib import Path

import pytest

from crimescene.api.chat_bootstrap import DEFAULT_DATA_ROOT, _locate_data_dir
from crimescene.db.neo4j_sync import find_source
from crimescene.ingest.case001_dataset import load_npc_cards
from crimescene.scenario.evidence_acquisition import (
    REVIEWED_FIND_CARDS,
    build_evidence_acquisition_setup,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.loaders.access_policy_loader import load_access_policies
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.scenario.schemas.game_state import EvidenceState


def get_real_data():
    root = Path(DEFAULT_DATA_ROOT)
    if not root.exists():
        pytest.skip("로컬 CASE-001 원본이 없습니다.")
    data_dir = _locate_data_dir(root)
    return (
        load_evidence_rules(find_source(root, "evidence_rules.json")),
        load_access_policies(data_dir / "access_policies.json"),
        load_npc_cards(data_dir / "npc_knowledge_cards.jsonl"),
    )


def test_ten_evidence_bindings_and_seven_topic_triggers():
    rules, policies, cards = get_real_data()
    setup = build_evidence_acquisition_setup(
        evidence_rules=rules,
        policies=policies,
        npc_cards=cards,
    )
    assert set(setup.policy_ids) == set(REVIEWED_FIND_CARDS)
    assert len(setup.triggers) == 7
    assert not any(trigger.grant_flags for trigger in setup.triggers)


def test_id_alone_never_grants_evidence():
    rules, policies, cards = get_real_data()
    setup = build_evidence_acquisition_setup(
        evidence_rules=rules,
        policies=policies,
        npc_cards=cards,
    )
    state = create_initial_state("test-evidence-permissions")
    for evidence_id, policy_id in setup.policy_ids.items():
        assert not setup.evaluator.is_allowed(
            policy_id,
            state,
            active_character_id=rules[evidence_id].holder,
        )


def test_e01_disclosed_card_allows_policy_but_no_other_evidence():
    rules, policies, cards = get_real_data()
    setup = build_evidence_acquisition_setup(
        evidence_rules=rules,
        policies=policies,
        npc_cards=cards,
    )
    state = create_initial_state("test-e01-permissions")
    state.disclosed_cards = ["K-C01-03"]
    assert setup.evaluator.is_allowed(
        setup.policy_ids["E01"],
        state,
        active_character_id="C01",
    )
    assert not setup.evaluator.is_allowed(
        setup.policy_ids["E04"],
        state,
        active_character_id="C04",
    )


def test_e04_requires_e01_presentation_and_disclosure():
    rules, policies, cards = get_real_data()
    setup = build_evidence_acquisition_setup(
        evidence_rules=rules,
        policies=policies,
        npc_cards=cards,
    )
    state = create_initial_state("test-e04-permissions")
    state.unlocked_characters.append("C04")
    state.evidence["E01"] = EvidenceState(stage="found")
    state.disclosed_cards = ["K-C04-03"]
    assert not setup.evaluator.is_allowed(
        setup.policy_ids["E04"],
        state,
        active_character_id="C04",
    )
    state.presented["C04"] = ["E01"]
    assert setup.evaluator.is_allowed(
        setup.policy_ids["E04"],
        state,
        active_character_id="C04",
    )


def test_forged_find_effect_is_rejected():
    rules, policies, cards = get_real_data()
    cards = [dict(card) for card in cards]
    target = next(card for card in cards if card["id"] == "K-C01-02")
    target["effects"] = {"find": ["E01"], "flags": []}
    with pytest.raises(ValueError, match="매핑 불일치"):
        build_evidence_acquisition_setup(
            evidence_rules=rules,
            policies=policies,
            npc_cards=cards,
        )


def test_missing_find_card_is_rejected():
    rules, policies, cards = get_real_data()
    cards = [card for card in cards if card["id"] != "K-C01-03"]
    with pytest.raises(ValueError, match="매핑 불일치"):
        build_evidence_acquisition_setup(
            evidence_rules=rules,
            policies=policies,
            npc_cards=cards,
        )
