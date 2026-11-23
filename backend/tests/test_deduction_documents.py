
"""Issue #132 - Deduction Agent 문서 접근 제어 테스트."""

import pytest

from crimescene.agents.contracts import AgentContext, AgentRequest, AgentType
from crimescene.agents.deduction_agent import DeductionAgent
from crimescene.agents.deduction_documents import (
    select_visible_deduction_documents,
)
from crimescene.agents.orchestrator import AgentOrchestrator
from crimescene.agents.registry import AgentRegistry
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GamePhase


def make_state(*evidence_ids):
    state = transition_phase(
        create_initial_state("DOC-132"),
        GamePhase.INVESTIGATION,
    )
    state.evidence = {
        item: EvidenceState(stage="found")
        for item in evidence_ids
    }
    return state


def make_document(
    *,
    source_ids=("E01",),
    protected=(),
    case_id="CASE-001",
):
    return PlayerDocument(
        doc_id="DOC-001",
        case_id=case_id,
        title="신기범 일정 기록",
        body="문서 본문은 내부 검토용입니다.",
        family="evidence",
        access_scope="collected_evidence",
        truth_status="documented_in_game",
        source_evidence_ids=list(source_ids),
        known_by_character_ids=[],
        source_doc_ids=[],
        required_evidence=[],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        protected_fact_ids=list(protected),
        incident_year=2026,
        incident_years=[],
        source_refs=[],
        record_id="REC-001",
        point_id="POINT-001",
        policy_id="POL-001",
        state_version="v1",
        content_version="v1",
        build_id="TEST",
        content_hash="test-hash",
        search_text="신기범 일정 기록",
    )


def make_evaluator(*, approved=True):
    policy = AccessPolicy(
        required_character=None,
        required_evidence=[],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
    )

    return PolicyEvaluator(
        {"POL-001": policy} if approved else {}
    )


def select(state, document, evaluator=None):
    return select_visible_deduction_documents(
        state=state,
        documents=[document],
        evaluator=evaluator or make_evaluator(),
        related_evidence_ids=("E01",),
    )


def test_collected_evidence_document_allowed():
    result = select(
        make_state("E01"),
        make_document(),
    )

    assert len(result) == 1
    assert result[0].doc_id == "DOC-001"
    assert result[0].evidence_ids == ("E01",)


def test_uncollected_linked_evidence_blocks_document():
    result = select(
        make_state("E01"),
        make_document(source_ids=("E01", "E02")),
    )

    assert result == ()


def test_unapproved_policy_blocks_document():
    result = select(
        make_state("E01"),
        make_document(),
        make_evaluator(approved=False),
    )

    assert result == ()


def test_protected_facts_block_document():
    result = select(
        make_state("E01"),
        make_document(protected=("SECRET-001",)),
    )

    assert result == ()


def test_other_case_document_blocked():
    result = select(
        make_state("E01"),
        make_document(case_id="CASE-999"),
    )

    assert result == ()


def test_document_body_not_exposed():
    result = select(
        make_state("E01"),
        make_document(),
    )

    serialized = result[0].model_dump_json()

    assert "문서 본문" not in serialized
    assert "content" not in serialized


def test_uncollected_query_evidence_rejected():
    with pytest.raises(PermissionError, match="미획득"):
        select_visible_deduction_documents(
            state=make_state("E01"),
            documents=[make_document()],
            evaluator=make_evaluator(),
            related_evidence_ids=("E02",),
        )


def make_deduction_agent(state, document, evaluator):
    return DeductionAgent(
        load_state=lambda session_id: state,
        evidence_rules={
            "E01": EvidenceRule(
                name="신기범 일정표",
                score=1,
                holder="C01",
                prerequisites=[],
                presentation=[],
                q=[],
            )
        },
        documents=(document,),
        evaluator=evaluator,
    )


def execute_deduction(agent, state):
    return agent.execute(
        AgentRequest(
            agent_type=AgentType.DEDUCTION,
            message="E01에 대해 검토해 주세요.",
        ),
        context=AgentContext.from_game_state(state),
    )


def test_deduction_agent_uses_authorized_document():
    state = make_state("E01")
    agent = make_deduction_agent(
        state,
        make_document(),
        make_evaluator(),
    )

    result = execute_deduction(agent, state)

    assert result.source_ids == ("E01",)
    assert len(result.documents) == 1
    assert result.documents[0].doc_id == "DOC-001"
    assert "신기범 일정 기록" in result.text
    assert "문서 본문은 내부 검토용" not in result.model_dump_json()


def test_deduction_agent_blocks_unapproved_document():
    state = make_state("E01")
    agent = make_deduction_agent(
        state,
        make_document(),
        make_evaluator(approved=False),
    )

    result = execute_deduction(agent, state)

    assert result.documents == ()
    assert "신기범 일정 기록" not in result.text


def test_deduction_agent_blocks_protected_document():
    state = make_state("E01")
    agent = make_deduction_agent(
        state,
        make_document(protected=("SECRET-001",)),
        make_evaluator(),
    )

    result = execute_deduction(agent, state)

    assert result.documents == ()
    assert "신기범 일정 기록" not in result.text


def test_deduction_agent_requires_document_policy():
    state = make_state("E01")

    with pytest.raises(TypeError, match="접근 정책"):
        DeductionAgent(
            load_state=lambda session_id: state,
            evidence_rules={},
            documents=(make_document(),),
        )


def test_deduction_documents_orchestrator_read_only():
    state = make_state("E01")
    before = state.model_dump(mode="json")

    agent = make_deduction_agent(
        state,
        make_document(),
        make_evaluator(),
    )

    orchestrator = AgentOrchestrator(
        AgentRegistry([agent]),
        load_state=lambda session_id: state,
    )

    result = orchestrator.execute(
        AgentRequest(
            agent_type=AgentType.DEDUCTION,
            message="E01에 대해 검토해 주세요.",
        ),
        context=AgentContext.from_game_state(state),
    )

    assert len(result.documents) == 1
    assert result.source_ids == ("E01",)
    assert state.model_dump(mode="json") == before
