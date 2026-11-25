"""Issue #156 - MCP Multi-Agent orchestration tests."""

from unittest.mock import AsyncMock, Mock

import pytest

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentType,
)
from crimescene.agents.deduction_agent import (
    DeductionResult,
    DeductionStatus,
)
from crimescene.agents.hint_agent import HintResult
from crimescene.agents.mcp_deduction import MCPDeductionAgent
from crimescene.agents.mcp_hint import MCPHintAgent
from crimescene.agents.mcp_orchestrator import (
    AgentCollaborationResult,
    MCPAgentOrchestrator,
)
from crimescene.agents.orchestrator import AgentExecutionTimeout
from crimescene.agents.tool_router import AgentToolRouter
from crimescene.mcp.client import (
    MCPToolExecutionError,
    MCPToolPermissionError,
    MCPToolTimeoutError,
)
from crimescene.mcp.server import create_readonly_mcp_server
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def make_runtime(collected=("E01", "E02")):
    rules = {
        evidence_id: EvidenceRule(
            name=evidence_id,
            score=score,
            holder=holder,
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for evidence_id, score, holder in (
            ("E01", 2, "C01"),
            ("E02", 3, "C02"),
        )
    }

    state = transition_phase(
        create_initial_state("workflow-player"),
        GamePhase.INVESTIGATION,
    )

    state.evidence = {
        evidence_id: EvidenceState(stage="found")
        for evidence_id in collected
    }

    state.score = sum(
        rules[evidence_id].score
        for evidence_id in collected
    )

    def load_state(_):
        return state

    def create_server(bound):
        return create_readonly_mcp_server(
            context=bound,
            evidence_rules=rules,
        )

    factory = Mock(side_effect=create_server)

    deduction = MCPDeductionAgent(
        load_state=load_state,
        evidence_rules=rules,
    )

    hint = MCPHintAgent(
        load_state=load_state,
        evidence_rules=rules,
    )

    orchestrator = MCPAgentOrchestrator(
        deduction_agent=deduction,
        hint_agent=hint,
        load_state=load_state,
        server_factory=factory,
    )

    context = AgentContext.from_game_state(state)

    return (
        state,
        context,
        orchestrator,
        deduction,
        hint,
        factory,
    )


def deduction_request(message="Review related records"):
    return AgentRequest(
        agent_type=AgentType.DEDUCTION,
        message=message,
    )


def hint_request(level=2):
    return AgentRequest(
        agent_type=AgentType.HINT,
        message=f"{level}\uB2E8\uACC4",
    )


def mock_search(monkeypatch, evidence_id="E02"):
    search = AsyncMock(
        return_value={
            "items": [
                {
                    "document_id": f"DOC-{evidence_id}",
                    "title": "Authorized evidence",
                    "excerpt": "Public records",
                    "evidence_ids": [evidence_id],
                }
            ]
        }
    )

    monkeypatch.setattr(
        AgentToolRouter,
        "search_authorized_evidence",
        search,
    )

    return search


@pytest.mark.anyio
async def test_single_deduction(monkeypatch):
    _, context, workflow, *_ = make_runtime()

    mock_search(monkeypatch)

    result = await workflow.execute_async(
        deduction_request(),
        context=context,
    )

    assert isinstance(result, DeductionResult)
    assert result.source_ids == ("E02",)


@pytest.mark.anyio
async def test_single_hint():
    _, context, workflow, *_ = make_runtime()

    result = await workflow.execute_async(
        hint_request(),
        context=context,
    )

    assert isinstance(result, HintResult)
    assert result.level == 2
    assert result.collected_count == 2


@pytest.mark.anyio
async def test_collaboration_transfers_sources(monkeypatch):
    _, context, workflow, _, hint, factory = make_runtime()

    search = mock_search(monkeypatch)

    hint_spy = AsyncMock(wraps=hint.execute_async)

    monkeypatch.setattr(
        hint,
        "execute_async",
        hint_spy,
    )

    result = await workflow.assist(
        deduction_request(),
        hint_request(2),
        context=context,
    )

    assert isinstance(
        result,
        AgentCollaborationResult,
    )

    assert result.deduction.source_ids == ("E02",)
    assert result.hint.source_ids == ("E02",)
    assert result.hint.level == 2

    forwarded = (
        hint_spy.call_args.kwargs["deduction_result"]
    )

    assert forwarded == result.deduction

    search.assert_awaited_once()
    factory.assert_called_once()


@pytest.mark.anyio
async def test_collaboration_level_one(monkeypatch):
    _, context, workflow, *_ = make_runtime()

    mock_search(monkeypatch)

    result = await workflow.assist(
        deduction_request(),
        hint_request(1),
        context=context,
    )

    assert result.deduction.source_ids == ("E02",)
    assert result.hint.level == 1
    assert result.hint.source_ids == ()


@pytest.mark.anyio
async def test_collaboration_level_three(monkeypatch):
    _, context, workflow, *_ = make_runtime()

    mock_search(monkeypatch)

    result = await workflow.assist(
        deduction_request(),
        hint_request(3),
        context=context,
    )

    assert result.hint.level == 3

    if context.unlocked_characters:
        assert result.hint.source_ids == ("E02",)

        assert (
            result.hint.suggested_character_id
            in context.unlocked_characters
        )
    else:
        assert result.hint.suggested_character_id is None


@pytest.mark.anyio
async def test_no_evidence_real_sdk_workflow():
    _, context, workflow, *_ = make_runtime(
        collected=()
    )

    result = await workflow.assist(
        deduction_request(),
        hint_request(2),
        context=context,
    )

    assert (
        result.deduction.status
        == DeductionStatus.INSUFFICIENT_EVIDENCE
    )

    assert result.deduction.source_ids == ()
    assert result.hint.source_ids == ()
    assert result.hint.collected_count == 0


@pytest.mark.anyio
async def test_npc_execution_rejected():
    _, context, workflow, _, _, factory = make_runtime()

    request = AgentRequest(
        agent_type=AgentType.NPC,
        message="NPC conversation",
    )

    with pytest.raises(MCPToolPermissionError):
        await workflow.execute_async(
            request,
            context=context,
        )

    factory.assert_not_called()


@pytest.mark.anyio
async def test_wrong_collaboration_order_rejected():
    _, context, workflow, _, _, factory = make_runtime()

    with pytest.raises(ValueError):
        await workflow.assist(
            hint_request(),
            deduction_request(),
            context=context,
        )

    factory.assert_not_called()


@pytest.mark.anyio
async def test_invalid_hint_level_rejected_before_search():
    _, context, workflow, _, _, factory = make_runtime()

    with pytest.raises(ValueError):
        await workflow.assist(
            deduction_request(),
            hint_request(4),
            context=context,
        )

    factory.assert_not_called()


@pytest.mark.anyio
async def test_stale_context_rejected():
    state, context, workflow, _, _, factory = make_runtime()

    state.revision += 1

    with pytest.raises(RuntimeError):
        await workflow.execute_async(
            hint_request(),
            context=context,
        )

    factory.assert_not_called()


@pytest.mark.anyio
async def test_cross_session_context_rejected():
    _, context, workflow, _, _, factory = make_runtime()

    foreign_context = context.model_copy(
        update={"session_id": "other-player"}
    )

    with pytest.raises(PermissionError):
        await workflow.execute_async(
            hint_request(),
            context=foreign_context,
        )

    factory.assert_not_called()


@pytest.mark.anyio
async def test_uncollected_deduction_result_rejected(
    monkeypatch,
):
    _, context, workflow, deduction, hint, _ = (
        make_runtime()
    )

    invalid = DeductionResult(
        agent_type=AgentType.DEDUCTION,
        text="Invalid evidence.",
        source_ids=("E10",),
        status=DeductionStatus.RELATED_EVIDENCE,
    )

    monkeypatch.setattr(
        deduction,
        "execute_async",
        AsyncMock(return_value=invalid),
    )

    hint_spy = AsyncMock()

    monkeypatch.setattr(
        hint,
        "execute_async",
        hint_spy,
    )

    with pytest.raises(MCPToolPermissionError):
        await workflow.assist(
            deduction_request(),
            hint_request(),
            context=context,
        )

    hint_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_locked_character_result_rejected(
    monkeypatch,
):
    _, context, workflow, _, hint, _ = make_runtime()

    baseline = hint.execute(
        hint_request(3),
        context=context,
    )

    invalid = baseline.model_copy(
        update={"suggested_character_id": "C99"}
    )

    monkeypatch.setattr(
        hint,
        "execute_async",
        AsyncMock(return_value=invalid),
    )

    with pytest.raises(MCPToolPermissionError):
        await workflow.execute_async(
            hint_request(3),
            context=context,
        )


@pytest.mark.anyio
async def test_state_change_during_handoff(
    monkeypatch,
):
    state, context, workflow, deduction, hint, _ = (
        make_runtime()
    )

    original = deduction.execute_async

    mock_search(monkeypatch)

    async def changed_state(*args, **kwargs):
        result = await original(*args, **kwargs)
        state.revision += 1
        return result

    monkeypatch.setattr(
        deduction,
        "execute_async",
        changed_state,
    )

    hint_spy = AsyncMock()

    monkeypatch.setattr(
        hint,
        "execute_async",
        hint_spy,
    )

    with pytest.raises(RuntimeError):
        await workflow.assist(
            deduction_request(),
            hint_request(),
            context=context,
        )

    hint_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_deduction_failure_stops_hint(
    monkeypatch,
):
    _, context, workflow, deduction, hint, _ = (
        make_runtime()
    )

    monkeypatch.setattr(
        deduction,
        "execute_async",
        AsyncMock(
            side_effect=MCPToolExecutionError(
                "Retrieval failed."
            )
        ),
    )

    hint_spy = AsyncMock()

    monkeypatch.setattr(
        hint,
        "execute_async",
        hint_spy,
    )

    with pytest.raises(MCPToolExecutionError):
        await workflow.assist(
            deduction_request(),
            hint_request(),
            context=context,
        )

    hint_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_timeout_converted_to_agent_timeout(
    monkeypatch,
):
    _, context, workflow, deduction, _, _ = (
        make_runtime()
    )

    monkeypatch.setattr(
        deduction,
        "execute_async",
        AsyncMock(
            side_effect=MCPToolTimeoutError(
                "MCP timed out."
            )
        ),
    )

    with pytest.raises(AgentExecutionTimeout):
        await workflow.execute_async(
            deduction_request(),
            context=context,
        )


@pytest.mark.anyio
async def test_missing_rag_fails_closed():
    _, context, workflow, *_ = make_runtime()

    with pytest.raises(MCPToolExecutionError):
        await workflow.assist(
            deduction_request(),
            hint_request(),
            context=context,
        )


@pytest.mark.anyio
async def test_collaboration_preserves_state(
    monkeypatch,
):
    state, context, workflow, *_ = make_runtime()

    before = state.model_dump(mode="json")

    mock_search(monkeypatch)

    await workflow.assist(
        deduction_request(),
        hint_request(),
        context=context,
    )

    assert state.model_dump(mode="json") == before
