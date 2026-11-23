
"""Issue #132 - Deduction Agent 권한 및 실행 테스트."""

import pytest

from crimescene.agents.contracts import AgentContext, AgentRequest, AgentType
from crimescene.agents.deduction_agent import (
    DeductionAgent,
    DeductionStatus,
)
from crimescene.agents.orchestrator import AgentOrchestrator
from crimescene.agents.registry import AgentRegistry
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)


def make_rule(name: str) -> EvidenceRule:
    return EvidenceRule(
        name=name,
        score=1,
        holder="C01",
        prerequisites=[],
        presentation=[],
        q=[],
    )


def make_state(*, collected: tuple[str, ...] = ()):
    state = transition_phase(
        create_initial_state("SESSION-132"),
        GamePhase.INVESTIGATION,
    )

    return state.model_copy(
        update={
            "evidence": {
                evidence_id: EvidenceState(stage="found")
                for evidence_id in collected
            }
        }
    )


def make_agent(state):
    rules = {
        "E01": make_rule("신기범 일정표"),
        "E02": make_rule("비공개 증거"),
    }

    return DeductionAgent(
        load_state=lambda session_id: state,
        evidence_rules=rules,
    )


def execute(agent, state, message):
    return agent.execute(
        AgentRequest(
            agent_type=AgentType.DEDUCTION,
            message=message,
        ),
        context=AgentContext.from_game_state(state),
    )


def test_related_collected_evidence():
    state = make_state(collected=("E01",))
    result = execute(
        make_agent(state),
        state,
        "E01이 이 사건과 관련이 있나요?",
    )

    assert result.status == DeductionStatus.RELATED_EVIDENCE
    assert result.source_ids == ("E01",)
    assert "신기범 일정표" in result.text
    assert result.verdict == "UNVERIFIED"


def test_insufficient_evidence():
    state = make_state()
    result = execute(
        make_agent(state),
        state,
        "범인은 누구인가요?",
    )

    assert result.status == DeductionStatus.INSUFFICIENT_EVIDENCE
    assert result.source_ids == ()
    assert result.contradiction == "NOT_DETERMINED"


def test_uncollected_evidence_id_rejected():
    state = make_state(collected=("E01",))

    with pytest.raises(PermissionError, match="사용할 수 없는"):
        execute(make_agent(state), state, "E02가 범행 도구인가요?")


def test_hidden_evidence_name_not_disclosed():
    state = make_state(collected=("E01",))
    result = execute(
        make_agent(state),
        state,
        "비공개 증거를 확인해 주세요.",
    )

    assert result.source_ids == ()
    assert "비공개 증거" not in result.text


def test_stale_context_rejected():
    state = make_state(collected=("E01",))
    agent = make_agent(state)

    stale_context = AgentContext.from_game_state(state).model_copy(
        update={"revision": state.revision - 1}
    )

    with pytest.raises(RuntimeError, match="스냅샷"):
        agent.execute(
            AgentRequest(
                agent_type=AgentType.DEDUCTION,
                message="E01을 검토해 주세요.",
            ),
            context=stale_context,
        )


def test_orchestrator_read_only_execution():
    state = make_state(collected=("E01",))
    before = state.model_dump(mode="json")

    agent = make_agent(state)

    orchestrator = AgentOrchestrator(
        AgentRegistry([agent]),
        load_state=lambda session_id: state,
    )

    result = orchestrator.execute(
        AgentRequest(
            agent_type=AgentType.DEDUCTION,
            message="E01을 검토해 주세요.",
        ),
        context=AgentContext.from_game_state(state),
    )

    assert result.source_ids == ("E01",)
    assert state.model_dump(mode="json") == before


from crimescene.agents.deduction_relations import (
    select_visible_deduction_relations,
)
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge


def make_edge(
    *,
    target="C02",
    scope="conditional",
    required_evidence=("E01",),
):
    return RelationshipSourceEdge.model_validate(
        {
            "case_id": "CASE-001",
            "edge_id": "REL-001",
            "source_id": "C01",
            "target_id": target,
            "relation": "KNOWS",
            "incident_year": 2026,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "temporal_precision": "day",
            "truth_status": "witness_statement",
            "source_doc_ids": [],
            "asserted_by": [],
            "access_scope": scope,
            "required_evidence": list(required_evidence),
            "required_presentations": [],
            "required_flags": [],
            "required_ending": None,
        }
    )


def test_visible_relation_with_collected_evidence():
    state = make_state(collected=("E01",))
    state.unlocked_characters.append("C02")

    relations = select_visible_deduction_relations(
        state=state,
        trusted_edges=[make_edge()],
        related_evidence_ids=("E01",),
    )

    assert len(relations) == 1
    assert relations[0].edge_id == "REL-001"
    assert relations[0].evidence_ids == ("E01",)


def test_locked_npc_relation_not_disclosed():
    state = make_state(collected=("E01",))

    relations = select_visible_deduction_relations(
        state=state,
        trusted_edges=[make_edge(target="C02")],
        related_evidence_ids=("E01",),
    )

    assert relations == ()


def test_uncollected_relation_not_disclosed():
    state = make_state(collected=("E01",))
    state.unlocked_characters.append("C02")

    relations = select_visible_deduction_relations(
        state=state,
        trusted_edges=[
            make_edge(required_evidence=("E02",)),
        ],
        related_evidence_ids=("E01",),
    )

    assert relations == ()


def test_ending_relation_not_disclosed():
    state = make_state(collected=("E01",))
    state.unlocked_characters.append("C02")

    relations = select_visible_deduction_relations(
        state=state,
        trusted_edges=[
            make_edge(
                scope="ending_only",
                required_evidence=("E01",),
            )
        ],
        related_evidence_ids=("E01",),
    )

    assert relations == ()


def test_deduction_agent_returns_authorized_relations():
    state = make_state(collected=("E01",))
    state.unlocked_characters.append("C02")

    agent = DeductionAgent(
        load_state=lambda session_id: state,
        evidence_rules={"E01": make_rule("신기범 일정표")},
        trusted_edges=[make_edge()],
    )

    result = execute(agent, state, "E01에 대해 추리해 주세요.")

    assert len(result.relations) == 1
    assert result.source_ids == ("E01",)
    assert result.verdict == "UNVERIFIED"
    assert result.contradiction == "NOT_DETERMINED"
