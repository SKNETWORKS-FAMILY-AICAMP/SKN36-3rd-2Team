"""Issue #156 - Agent Tool Router integration and security tests."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from crimescene.agents.contracts import AgentContext, AgentType
from crimescene.agents.tool_router import (
    AgentToolRouter,
    get_allowed_tools,
)
from crimescene.mcp.client import (
    MCPToolClient,
    MCPToolExecutionError,
    MCPToolPermissionError,
    MCPToolValidationError,
)
from crimescene.mcp.context import BoundMCPContext
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


def make_rules():
    return {
        evidence_id: EvidenceRule(
            name=evidence_id,
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for evidence_id, score in (
            ("E01", 2),
            ("E02", 3),
        )
    }


def make_state(session_id="router-a", collected=()):
    state = transition_phase(
        create_initial_state(session_id),
        GamePhase.INVESTIGATION,
    )

    state.evidence = {
        evidence_id: EvidenceState(stage="found")
        for evidence_id in collected
    }

    state.score = sum(
        make_rules()[evidence_id].score
        for evidence_id in collected
    )

    return state


def make_router(
    state,
    agent_type=AgentType.DEDUCTION,
):
    server = create_readonly_mcp_server(
        context=BoundMCPContext.from_owned_game_state(
            state=state,
            load_state=lambda _: state,
        ),
        evidence_rules=make_rules(),
    )

    return AgentToolRouter(
        agent_type=agent_type,
        context=AgentContext.from_game_state(state),
        server=server,
    )


def mock_tool(monkeypatch, payload):
    tool = AsyncMock(return_value=payload)

    monkeypatch.setattr(
        MCPToolClient,
        "call_tool",
        tool,
    )

    return tool


def make_evidence_item():
    return {
        "document_id": "DOC-E01",
        "title": "Approved evidence",
        "excerpt": "Public evidence content",
        "evidence_ids": ["E01"],
    }


# Agent-specific tool policies.


def test_deduction_allowlist():
    assert get_allowed_tools(
        AgentType.DEDUCTION
    ) == frozenset({
        "get_game_context",
        "get_investigation_progress",
        "search_authorized_evidence",
    })


def test_hint_allowlist():
    assert get_allowed_tools(
        AgentType.HINT
    ) == frozenset({
        "get_game_context",
        "get_investigation_progress",
    })


def test_npc_router_not_enabled():
    with pytest.raises(MCPToolPermissionError):
        make_router(
            make_state(),
            AgentType.NPC,
        )


def test_invalid_agent_type():
    with pytest.raises(TypeError):
        get_allowed_tools("deduction")


def test_allowlist_immutable():
    router = make_router(make_state())

    assert isinstance(
        router.allowed_tools,
        frozenset,
    )

    assert "get_npc_knowledge" not in router.allowed_tools


@pytest.mark.anyio
async def test_hint_cannot_search_evidence():
    router = make_router(
        make_state(),
        AgentType.HINT,
    )

    with pytest.raises(MCPToolPermissionError):
        await router.search_authorized_evidence(
            "evidence"
        )


# Actual MCP SDK calls.


@pytest.mark.anyio
@pytest.mark.parametrize(
    "agent_type",
    [AgentType.DEDUCTION, AgentType.HINT],
)
async def test_real_game_context(agent_type):
    state = make_state(collected=("E01",))

    router = make_router(state, agent_type)

    result = await router.get_game_context()

    assert router.agent_type == agent_type
    assert router.context.revision == state.revision
    assert result["revision"] == state.revision
    assert result["collected_evidence_ids"] == ["E01"]
    assert "session_id" not in result


@pytest.mark.anyio
async def test_real_investigation_progress():
    router = make_router(
        make_state(collected=("E01",)),
        AgentType.HINT,
    )

    result = await router.get_investigation_progress()

    assert result["collected_count"] == 1
    assert result["total_count"] == 2
    assert result["collection_rate"] == 50.0
    assert result["score"] == 2


@pytest.mark.anyio
async def test_readonly_state():
    state = make_state(collected=("E01",))
    original = state.model_dump(mode="json")

    router = make_router(state)

    await router.get_game_context()
    await router.get_investigation_progress()

    assert state.model_dump(mode="json") == original


@pytest.mark.anyio
async def test_session_isolation():
    router_a = make_router(
        make_state("router-a", ("E01",))
    )

    router_b = make_router(
        make_state("router-b", ("E02",))
    )

    result_a, result_b = await asyncio.gather(
        router_a.get_game_context(),
        router_b.get_game_context(),
    )

    assert result_a["collected_evidence_ids"] == ["E01"]
    assert result_b["collected_evidence_ids"] == ["E02"]


@pytest.mark.anyio
async def test_stale_revision_rejected():
    state = make_state()

    router = make_router(state)

    state.revision += 1

    with pytest.raises(MCPToolExecutionError):
        await router.get_game_context()


@pytest.mark.anyio
async def test_missing_rag_fails_closed():
    router = make_router(
        make_state(collected=("E01",))
    )

    with pytest.raises(MCPToolExecutionError):
        await router.search_authorized_evidence(
            "E01"
        )


# Context consistency checks.


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("revision", 999),
        ("phase", "ENDING"),
        ("current_chapter", "CH99"),
        ("collected_evidence_ids", ["E02"]),
        ("unlocked_character_ids", ["C99"]),
    ],
)
async def test_context_mismatch(
    monkeypatch,
    field,
    value,
):
    router = make_router(
        make_state(collected=("E01",))
    )

    payload = await router.get_game_context()

    payload[field] = value

    mock_tool(monkeypatch, payload)

    with pytest.raises(MCPToolValidationError):
        await router.get_game_context()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("current_chapter", "CH99"),
        ("collected_count", 0),
        ("total_count", 0),
        ("collection_rate", 101.0),
        ("collection_rate", -1.0),
        ("score", -1),
        ("total_score", 0),
    ],
)
async def test_invalid_progress(
    monkeypatch,
    field,
    value,
):
    router = make_router(
        make_state(collected=("E01",))
    )

    payload = await router.get_investigation_progress()

    payload[field] = value

    mock_tool(monkeypatch, payload)

    with pytest.raises(MCPToolValidationError):
        await router.get_investigation_progress()


# Authorized evidence result validation.


@pytest.mark.anyio
async def test_authorized_search_result(monkeypatch):
    router = make_router(
        make_state(collected=("E01",))
    )

    payload = {
        "items": [make_evidence_item()]
    }

    tool = mock_tool(monkeypatch, payload)

    result = await router.search_authorized_evidence(
        "E01 evidence",
        limit=2,
    )

    assert result == payload

    tool.assert_awaited_once_with(
        "search_authorized_evidence",
        {
            "query": "E01 evidence",
            "limit": 2,
        },
    )


@pytest.mark.anyio
async def test_empty_search_result(monkeypatch):
    router = make_router(make_state())

    mock_tool(
        monkeypatch,
        {"items": []},
    )

    assert await router.search_authorized_evidence(
        "evidence"
    ) == {"items": []}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "evidence_ids",
    [
        [],
        ["E02"],
        ["E01", "E02"],
        ["E99"],
    ],
)
async def test_uncollected_evidence_rejected(
    monkeypatch,
    evidence_ids,
):
    router = make_router(
        make_state(collected=("E01",))
    )

    item = make_evidence_item()
    item["evidence_ids"] = evidence_ids

    mock_tool(
        monkeypatch,
        {"items": [item]},
    )

    with pytest.raises(MCPToolPermissionError):
        await router.search_authorized_evidence(
            "evidence"
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "field",
    [
        "document_id",
        "title",
        "excerpt",
    ],
)
async def test_blank_document_fields(
    monkeypatch,
    field,
):
    router = make_router(
        make_state(collected=("E01",))
    )

    item = make_evidence_item()
    item[field] = "   "

    mock_tool(
        monkeypatch,
        {"items": [item]},
    )

    with pytest.raises(MCPToolValidationError):
        await router.search_authorized_evidence(
            "evidence"
        )


@pytest.mark.anyio
async def test_duplicate_documents_rejected(
    monkeypatch,
):
    router = make_router(
        make_state(collected=("E01",))
    )

    mock_tool(
        monkeypatch,
        {
            "items": [
                make_evidence_item(),
                make_evidence_item(),
            ]
        },
    )

    with pytest.raises(MCPToolValidationError):
        await router.search_authorized_evidence(
            "evidence"
        )


@pytest.mark.anyio
async def test_search_limit_enforced(monkeypatch):
    router = make_router(
        make_state(collected=("E01",))
    )

    first = make_evidence_item()
    second = make_evidence_item()
    second["document_id"] = "DOC-E01-2"

    mock_tool(
        monkeypatch,
        {"items": [first, second]},
    )

    with pytest.raises(MCPToolValidationError):
        await router.search_authorized_evidence(
            "evidence",
            limit=1,
        )


@pytest.mark.anyio
async def test_service_failure_propagates(
    monkeypatch,
):
    router = make_router(make_state())

    tool = AsyncMock(
        side_effect=MCPToolExecutionError(
            "MCP service unavailable."
        )
    )

    monkeypatch.setattr(
        MCPToolClient,
        "call_tool",
        tool,
    )

    with pytest.raises(MCPToolExecutionError):
        await router.get_game_context()
