
"""Issue #129 - Multi-Agent 실행 계약 테스트."""

import pytest
from pydantic import ValidationError

from crimescene.agents.contracts import (
    AgentContext,
    AgentExecutor,
    AgentRequest,
    AgentResult,
    AgentType,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import EvidenceState


def test_agent_request_valid():
    request = AgentRequest(
        agent_type=AgentType.NPC,
        message="  안녕하세요  ",
        presented_evidence_id="E01",
    )

    assert request.message == "안녕하세요"
    assert request.agent_type == AgentType.NPC
    assert request.presented_evidence_id == "E01"


@pytest.mark.parametrize("message", ["", " ", "\n\t", "a" * 201])
def test_agent_request_invalid_message(message):
    with pytest.raises(ValidationError):
        AgentRequest(agent_type="npc", message=message)


def test_unknown_agent_rejected():
    with pytest.raises(ValidationError):
        AgentRequest(agent_type="admin", message="테스트")


@pytest.mark.parametrize(
    "field",
    ["session_id", "case_id", "revision", "permissions"],
)
def test_client_cannot_supply_authority_fields(field):
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(
            {
                "agent_type": "npc",
                "message": "테스트",
                field: "forged-value",
            }
        )


@pytest.mark.parametrize("agent_type", ["deduction", "hint"])
def test_evidence_presentation_npc_only(agent_type):
    with pytest.raises(ValidationError):
        AgentRequest(
            agent_type=agent_type,
            message="증거를 확인해 주세요",
            presented_evidence_id="E01",
        )


def test_invalid_evidence_id_rejected():
    with pytest.raises(ValidationError):
        AgentRequest(
            agent_type="npc",
            message="증거 제시",
            presented_evidence_id="E99",
        )


def test_context_from_game_state():
    state = create_initial_state("test-session-001")

    context = AgentContext.from_game_state(
        state,
        active_character_id="C01",
    )

    assert context.session_id == state.session_id
    assert context.case_id == "CASE-001"
    assert context.revision == 0
    assert context.active_character_id == "C01"
    assert context.collected_evidence_ids == ()


def test_locked_npc_rejected():
    state = create_initial_state("test-session-002")

    with pytest.raises(ValidationError):
        AgentContext.from_game_state(
            state,
            active_character_id="C02",
        )


def test_context_is_snapshot():
    state = create_initial_state("test-session-003")
    state.evidence["E01"] = EvidenceState(stage="found")

    context = AgentContext.from_game_state(state)

    # 스냅샷 생성 후 원본 상태 변경
    state.evidence["E02"] = EvidenceState(stage="found")
    state.revision += 1

    assert context.collected_evidence_ids == ("E01",)
    assert context.revision == 0


def test_context_is_frozen():
    state = create_initial_state("test-session-004")
    context = AgentContext.from_game_state(state)

    with pytest.raises(ValidationError):
        context.revision = 999


def test_agent_result_valid():
    result = AgentResult(
        agent_type=AgentType.HINT,
        text="이미 확보한 증거를 다시 확인해 보세요.",
        source_ids=("E01",),
    )

    assert result.agent_type == AgentType.HINT
    assert result.source_ids == ("E01",)


def test_agent_executor_contract():
    """공통 Agent 인터페이스를 구현한 테스트용 Agent."""

    class MockHintAgent:
        @property
        def agent_type(self) -> AgentType:
            return AgentType.HINT

        def execute(
            self,
            request: AgentRequest,
            *,
            context: AgentContext,
        ) -> AgentResult:
            if request.agent_type != self.agent_type:
                raise ValueError("Agent 유형 불일치")

            return AgentResult(
                agent_type=self.agent_type,
                text=f"{context.current_chapter} 조사 힌트",
            )

    agent: AgentExecutor = MockHintAgent()

    context = AgentContext.from_game_state(
        create_initial_state("test-session-005")
    )
    request = AgentRequest(
        agent_type=AgentType.HINT,
        message="힌트를 알려주세요",
    )

    result = agent.execute(request, context=context)

    assert result.agent_type == AgentType.HINT
    assert result.text == "CH00 조사 힌트"
