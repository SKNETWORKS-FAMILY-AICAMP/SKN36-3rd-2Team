"""Issue #155 - MCP Client execution and security tests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from crimescene.mcp import client as client_module
from crimescene.mcp.client import (
    SUPPORTED_TOOLS,
    MCPToolClient,
    MCPToolExecutionError,
    MCPToolPermissionError,
    MCPToolTimeoutError,
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


def make_state(session_id="player-a", collected=()):
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


def make_client(
    state,
    allowed_tools=SUPPORTED_TOOLS,
    timeout_seconds=15.0,
):
    context = BoundMCPContext.from_owned_game_state(
        state=state,
        load_state=lambda _: state,
    )

    server = create_readonly_mcp_server(
        context=context,
        evidence_rules=make_rules(),
    )

    return MCPToolClient(
        server=server,
        allowed_tools=allowed_tools,
        timeout_seconds=timeout_seconds,
    )


def context_payload():
    return {
        "phase": "INVESTIGATION",
        "current_chapter": "CH00",
        "unlocked_chapters": ["CH00"],
        "unlocked_character_ids": ["C01"],
        "collected_evidence_ids": ["E01"],
        "revision": 1,
    }


@pytest.fixture
def sdk_mock(monkeypatch):
    connection = MagicMock()

    connection.call_tool = AsyncMock(
        return_value=SimpleNamespace(
            is_error=False,
            structured_content=context_payload(),
        )
    )

    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=connection)
    manager.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=manager)

    monkeypatch.setattr(client_module, "Client", factory)

    return factory, manager, connection


# Actual MCP protocol integration.


@pytest.mark.anyio
async def test_real_game_context():
    state = make_state(collected=("E01",))
    client = make_client(state)

    result = await client.call_tool("get_game_context")

    assert result["collected_evidence_ids"] == ["E01"]
    assert result["revision"] == state.revision
    assert result["current_chapter"] == "CH00"
    assert "session_id" not in result


@pytest.mark.anyio
async def test_real_progress():
    client = make_client(make_state(collected=("E01",)))

    result = await client.call_tool(
        "get_investigation_progress"
    )

    assert result["collected_count"] == 1
    assert result["total_count"] == 2
    assert result["collection_rate"] == 50.0
    assert result["score"] == 2


@pytest.mark.anyio
async def test_real_readonly_state():
    state = make_state(collected=("E01",))
    before = state.model_dump(mode="json")

    client = make_client(state)

    await client.call_tool("get_game_context")
    await client.call_tool("get_investigation_progress")

    assert state.model_dump(mode="json") == before


@pytest.mark.anyio
async def test_real_session_isolation():
    client_a = make_client(
        make_state("player-a", ("E01",))
    )

    client_b = make_client(
        make_state("player-b", ("E02",))
    )

    result_a, result_b = await asyncio.gather(
        client_a.call_tool("get_game_context"),
        client_b.call_tool("get_game_context"),
    )

    assert result_a["collected_evidence_ids"] == ["E01"]
    assert result_b["collected_evidence_ids"] == ["E02"]


@pytest.mark.anyio
async def test_real_stale_revision():
    state = make_state()
    client = make_client(state)

    state.revision += 1

    with pytest.raises(MCPToolExecutionError):
        await client.call_tool("get_game_context")


@pytest.mark.anyio
async def test_real_missing_rag():
    client = make_client(make_state())

    with pytest.raises(MCPToolExecutionError):
        await client.call_tool(
            "search_authorized_evidence",
            {"query": "evidence"},
        )


# Allowlist and input validation.


def test_allowlist_is_immutable():
    allowed = {"get_game_context"}
    client = make_client(make_state(), allowed)

    allowed.add("get_npc_knowledge")

    assert client.allowed_tools == frozenset({
        "get_game_context"
    })


def test_invalid_allowlist():
    with pytest.raises(MCPToolPermissionError):
        make_client(make_state(), {"unlock_chapter"})


def test_empty_allowlist():
    with pytest.raises(ValueError):
        make_client(make_state(), set())


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name",
    [
        "get_npc_knowledge",
        "search_authorized_evidence",
        "unlock_chapter",
        "update_game_state",
        "",
    ],
)
async def test_forbidden_tools(sdk_mock, tool_name):
    factory, _, _ = sdk_mock

    client = make_client(
        make_state(),
        {"get_game_context"},
    )

    with pytest.raises(MCPToolPermissionError):
        await client.call_tool(tool_name)

    factory.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "arguments",
    [
        {"session_id": "other-player"},
        {"revision": 999},
        {"case_id": "CASE-999"},
        {"token": "forged-token"},
        {"character_id": "C10"},
        [],
    ],
)
async def test_invalid_context_arguments(sdk_mock, arguments):
    factory, _, _ = sdk_mock
    client = make_client(make_state())

    with pytest.raises(MCPToolValidationError):
        await client.call_tool(
            "get_game_context",
            arguments,
        )

    factory.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": ""},
        {"query": "   "},
        {"query": 123},
        {"query": "a" * 201},
        {"query": "evidence", "limit": 0},
        {"query": "evidence", "limit": 6},
        {"query": "evidence", "limit": True},
        {"query": "evidence", "limit": "3"},
        {"query": "evidence", "limit": 3.0},
        {"query": "evidence", "session_id": "other"},
        {"query": "evidence", "revision": 999},
        {"query": "evidence", "include_hidden": True},
    ],
)
async def test_invalid_search_arguments(sdk_mock, arguments):
    factory, _, _ = sdk_mock
    client = make_client(make_state())

    with pytest.raises(MCPToolValidationError):
        await client.call_tool(
            "search_authorized_evidence",
            arguments,
        )

    factory.assert_not_called()


@pytest.mark.anyio
async def test_valid_search_arguments(sdk_mock):
    _, manager, connection = sdk_mock

    payload = {
        "items": [
            {
                "document_id": "DOC-E01",
                "title": "Evidence",
                "evidence_ids": ["E01"],
                "excerpt": "Approved content",
            }
        ]
    }

    connection.call_tool.return_value = SimpleNamespace(
        is_error=False,
        structured_content=payload,
    )

    client = make_client(make_state(collected=("E01",)))

    result = await client.call_tool(
        "search_authorized_evidence",
        {"query": "  evidence  "},
    )

    assert result == payload

    connection.call_tool.assert_awaited_once_with(
        "search_authorized_evidence",
        {"query": "evidence", "limit": 3},
        read_timeout_seconds=15.0,
    )

    manager.__aexit__.assert_awaited_once()


# Structured response validation.


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {**context_payload(), "revision": "1"},
        {**context_payload(), "revision": True},
        {**context_payload(), "session_id": "other"},
        {**context_payload(), "collected_evidence_ids": [123]},
    ],
)
async def test_invalid_output(sdk_mock, payload):
    _, manager, connection = sdk_mock

    connection.call_tool.return_value = SimpleNamespace(
        is_error=False,
        structured_content=payload,
    )

    client = make_client(make_state())

    with pytest.raises(MCPToolValidationError):
        await client.call_tool("get_game_context")

    manager.__aexit__.assert_awaited_once()


@pytest.mark.anyio
async def test_nested_extra_field(sdk_mock):
    _, _, connection = sdk_mock

    connection.call_tool.return_value = SimpleNamespace(
        is_error=False,
        structured_content={
            "items": [
                {
                    "document_id": "DOC-E01",
                    "title": "Evidence",
                    "evidence_ids": ["E01"],
                    "excerpt": "Approved content",
                    "private_answer": "SECRET",
                }
            ]
        },
    )

    client = make_client(make_state(collected=("E01",)))

    with pytest.raises(MCPToolValidationError):
        await client.call_tool(
            "search_authorized_evidence",
            {"query": "evidence"},
        )


@pytest.mark.anyio
async def test_tool_error_sanitized(sdk_mock):
    _, manager, connection = sdk_mock

    connection.call_tool.return_value = SimpleNamespace(
        is_error=True,
        structured_content={"secret": "internal-token"},
    )

    client = make_client(make_state())

    with pytest.raises(MCPToolExecutionError) as error:
        await client.call_tool("get_game_context")

    assert "internal-token" not in str(error.value)

    manager.__aexit__.assert_awaited_once()


# Timeout and SDK lifecycle.


@pytest.mark.parametrize(
    "timeout",
    [0, -1, 121, True, "15", float("inf"), float("nan")],
)
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        make_client(
            make_state(),
            timeout_seconds=timeout,
        )


@pytest.mark.anyio
async def test_timeout_releases_client(sdk_mock):
    _, manager, connection = sdk_mock

    async def slow_call(*args, **kwargs):
        await asyncio.sleep(10)

    connection.call_tool.side_effect = slow_call

    client = make_client(
        make_state(),
        timeout_seconds=0.05,
    )

    with pytest.raises(MCPToolTimeoutError):
        await client.call_tool("get_game_context")

    manager.__aexit__.assert_awaited_once()


@pytest.mark.anyio
async def test_connection_error(sdk_mock):
    _, manager, _ = sdk_mock

    manager.__aenter__.side_effect = OSError(
        "private-host:6333 secret-token"
    )

    client = make_client(make_state())

    with pytest.raises(MCPToolExecutionError) as error:
        await client.call_tool("get_game_context")

    assert "private-host" not in str(error.value)
    assert "secret-token" not in str(error.value)


@pytest.mark.anyio
async def test_client_lifecycle(sdk_mock):
    factory, manager, connection = sdk_mock
    client = make_client(make_state())

    await client.call_tool("get_game_context")

    factory.assert_called_once()

    assert factory.call_args.kwargs["cache"] is None
    assert factory.call_args.kwargs["raise_exceptions"] is False

    manager.__aenter__.assert_awaited_once()
    manager.__aexit__.assert_awaited_once()
    connection.call_tool.assert_awaited_once()


@pytest.mark.anyio
async def test_client_closed_on_error(sdk_mock):
    _, manager, connection = sdk_mock

    connection.call_tool.side_effect = RuntimeError(
        "internal error"
    )

    client = make_client(make_state())

    with pytest.raises(MCPToolExecutionError):
        await client.call_tool("get_game_context")

    manager.__aexit__.assert_awaited_once()


@pytest.mark.anyio
async def test_client_reusable_after_error(sdk_mock):
    factory, manager, connection = sdk_mock

    connection.call_tool.side_effect = [
        RuntimeError("temporary failure"),
        SimpleNamespace(
            is_error=False,
            structured_content=context_payload(),
        ),
    ]

    client = make_client(make_state())

    with pytest.raises(MCPToolExecutionError):
        await client.call_tool("get_game_context")

    result = await client.call_tool("get_game_context")

    assert result == context_payload()
    assert factory.call_count == 2
    assert manager.__aexit__.await_count == 2
