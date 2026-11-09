"""Issue #28 - 실제 CASE-001 증거 및 NPC 해금 검증."""

from pathlib import Path

import pytest

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.scenario.evidence_service import collect_evidence_atomic
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.loaders.evidence_loader import (
    load_evidence_rules,
)
from crimescene.scenario.loaders.unlock_graph_loader import (
    load_case001_unlock_rules,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GamePhase
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

ROOT = Path(__file__).resolve().parents[2] / ".local" / "case001_v7_1"

EVIDENCE_ORDER = (
    "E01",
    "E04",
    "E10",
    "E02",
    "E03",
    "E05",
    "E06",
    "E07",
    "E08",
    "E09",
)


def load_real_rules():
    graph_files = list(ROOT.glob("*/data/unlock_graph.json"))
    evidence_files = list(ROOT.glob("*/data/evidence_rules.json"))

    if not graph_files or not evidence_files:
        pytest.skip("로컬 CASE-001 데이터가 없습니다.")

    assert len(graph_files) == 1
    assert len(evidence_files) == 1

    return (
        load_case001_unlock_rules(graph_files[0]),
        load_evidence_rules(evidence_files[0]),
    )


def test_real_npc_unlock_conditions():
    config, _ = load_real_rules()

    expected = {
        "C02": {"E01"},
        "C03": {"E04"},
        "C04": {"E01"},
        "C05": {"E01"},
        "C06": {"E02"},
        "C07": {"E02"},
        "C08": {"E03"},
        "C09": {"E10"},
        "C10": {"E03"},
    }

    assert len(config.npc_rules) == 9

    for npc_id, required in expected.items():
        assert config.npc_rules[npc_id].required_evidence == required


def test_real_flag_requirements():
    config, _ = load_real_rules()

    assert config.flag_requirements == {
        "L01": {"E03"},
        "L02": {"E03", "E04"},
        "L03": {"E05"},
        "L04": {"E01"},
        "L05": {"E07"},
    }


def test_all_evidence_and_npcs_reachable(tmp_path):
    config, evidence_rules = load_real_rules()

    repository = SQLiteCase001Repository(tmp_path / "case001.sqlite3")

    store = NPCSessionStore(repository=repository)

    state = create_initial_state("issue28-real-test")

    store.select_npc(state, "C01")
    repository.register_state(state)

    investigation = transition_phase(
        state,
        GamePhase.INVESTIGATION,
    )

    state = repository.commit_state(
        expected_state=state,
        updated_state=investigation,
    )

    # 실제 수집 정책은 아직 연결 전입니다.
    # 이 테스트는 증거 진행 경로를 검증하는 전용 정책을 사용합니다.
    policy_ids = {}
    policies = {}

    for evidence_id, rule in evidence_rules.items():
        policy_id = f"POL-TEST-{evidence_id}"

        policy_ids[evidence_id] = policy_id

        policies[policy_id] = AccessPolicy(
            required_evidence=[],
            required_presentations=[],
            required_flags=[],
            required_ending=None,
            required_topics=[],
            required_disclosed_cards=[],
            required_character=rule.holder,
        )

    evaluator = PolicyEvaluator(policies)

    for evidence_id in EVIDENCE_ORDER:
        rule = evidence_rules[evidence_id]

        # 해당 NPC가 이미 해금되어 있어야 증거를 획득할 수 있습니다.
        assert rule.holder in state.unlocked_characters

        # 모든 선행 증거를 수집한 상태여야 합니다.
        assert set(rule.prerequisites).issubset(state.evidence)

        store.select_npc(state, rule.holder)

        result = collect_evidence_atomic(
            session_id=state.session_id,
            evidence_id=evidence_id,
            active_character_id=rule.holder,
            repository=repository,
            evidence_rules=evidence_rules,
            acquisition_policy_ids=policy_ids,
            evaluator=evaluator,
            unlock_rules=config.npc_rules,
        )

        assert result.created is True

        state = result.state

        # 실제 SQLite 상태와 메모리 상태가 일치해야 합니다.
        assert repository.load_state(state.session_id) == state

    assert set(state.evidence) == set(evidence_rules)
    assert set(state.unlocked_characters) == set(EXPECTED_CHARACTER_IDS)

    assert len(state.evidence) == 10
    assert len(state.unlocked_characters) == 10

    assert state.score == 21
    assert state.revision == 11
