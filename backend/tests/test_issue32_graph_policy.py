
"""Issue #32 - CASE-001 Graph 접근 정책 회귀 테스트."""

from pathlib import Path

import pytest

from crimescene.retriever.graph_search import is_relation_visible
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.loaders.relationship_loader import load_relationship_edges
from crimescene.scenario.schemas.game_state import GamePhase, GameState


@pytest.fixture(scope="module")
def edges():
    root = Path(__file__).resolve().parents[2] / ".local" / "case001_v7_1"
    matches = list(root.rglob("relationship_edges_source.json"))

    if not matches:
        pytest.skip("CASE-001 로컬 관계 데이터 없음")

    if len(matches) != 1:
        pytest.fail("관계 데이터 경로가 중복되었습니다.")

    result = load_relationship_edges(matches[0])
    assert len(result) == 37
    return result


def make_satisfied_state(edge):
    """관계 공개 조건을 충족하는 테스트 상태를 생성합니다."""
    state = create_initial_state("issue32-graph-policy")

    evidence_ids = set(edge.required_evidence)
    presented = {}

    for value in edge.required_presentations:
        npc_id, evidence_id = value.split(":")
        evidence_ids.add(evidence_id)
        presented.setdefault(npc_id, []).append(evidence_id)

    ending = edge.required_ending
    outcome = (
        "SUCCESS" if ending == "DEEP"
        else ending if ending is not None
        else "ONGOING"
    )

    return GameState.model_validate({
        **state.model_dump(mode="python"),
        "phase": (
            GamePhase.FINISHED
            if ending is not None
            else GamePhase.INVESTIGATION
        ),
        "unlocked_characters": [
            f"C{i:02d}" for i in range(1, 11)
        ],
        "evidence": {
            eid: {"stage": "found"}
            for eid in evidence_ids
        },
        "presented": presented,
        "flags": list(edge.required_flags),
        "outcome": outcome,
        "deep_eligible": ending == "DEEP",
    })


def test_unmet_conditions_block_private_relations(edges):
    """초기 상태에서 조건부·엔딩 전용 관계가 공개되지 않아야 합니다."""
    initial = create_initial_state("issue32-locked")

    for edge in edges:
        allowed = is_relation_visible(edge, initial)

        if edge.access_scope == "public":
            assert allowed, edge.edge_id
        else:
            assert not allowed, (
                f"초기 상태에서 비공개 관계 유출: {edge.edge_id}"
            )


def test_satisfied_conditions_unlock_relations(edges):
    """각 관계의 공개 조건을 충족하면 접근 가능해야 합니다."""
    for edge in edges:
        state = make_satisfied_state(edge)

        assert is_relation_visible(edge, state), (
            f"정상적인 관계 해금 실패: {edge.edge_id}"
        )


def test_deep_ending_requires_eligibility(edges):
    """심층 엔딩 관계는 일반 성공 엔딩에서 차단되어야 합니다."""
    deep_edges = [
        edge for edge in edges
        if edge.required_ending == "DEEP"
    ]

    if not deep_edges:
        pytest.skip("DEEP 전용 관계 없음")

    for edge in deep_edges:
        allowed_state = make_satisfied_state(edge)

        normal_state = allowed_state.model_copy(
            update={"deep_eligible": False}
        )

        assert not is_relation_visible(edge, normal_state)
        assert is_relation_visible(edge, allowed_state)
