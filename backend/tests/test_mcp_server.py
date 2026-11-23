
"""Issue #134 - 실제 MCP 프로토콜 호출 및 세션 격리 테스트."""

import asyncio

import pytest
from mcp import Client

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
        "E01": EvidenceRule(
            name="첫 번째 증거",
            score=2,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
        "E02": EvidenceRule(
            name="비공개 증거",
            score=3,
            holder="C02",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
    }


def make_state(session_id="mcp-a", collected=()):
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


def make_server(state):
    context = BoundMCPContext.from_owned_game_state(
        state=state,
        load_state=lambda _: state,
    )

    return create_readonly_mcp_server(
        context=context,
        evidence_rules=make_rules(),
    )


@pytest.mark.anyio
async def test_mcp_lists_registered_tools():
    server = make_server(make_state())

    async with Client(server) as client:
        listed = await client.list_tools()

    names = {tool.name for tool in listed.tools}

    assert names == {
        "get_game_context",
        "get_investigation_progress",
        "get_npc_knowledge",
        "search_authorized_evidence",
    }

    for tool in listed.tools:
        # 구조화 출력 스키마가 반드시 등록되어야 합니다.
        assert tool.output_schema is not None
        assert tool.output_schema["type"] == "object"

        # 인증 정보는 LLM이 전달하는 Tool 인자에 포함하지 않습니다.
        properties = tool.input_schema.get("properties", {})
        assert "session_id" not in properties
        assert "case_id" not in properties
        assert "token" not in properties


@pytest.mark.anyio
async def test_get_game_context_via_mcp():
    state = make_state(collected=("E01",))
    server = make_server(state)

    async with Client(server) as client:
        result = await client.call_tool("get_game_context", {})

    assert not result.is_error

    data = result.structured_content
    assert data is not None
    assert data["current_chapter"] == "CH00"
    assert data["collected_evidence_ids"] == ["E01"]
    assert data["unlocked_character_ids"] == ["C01"]
    assert "E02" not in str(data)
    assert "mcp-a" not in str(data)


@pytest.mark.anyio
async def test_get_investigation_progress_via_mcp():
    state = make_state(collected=("E01",))
    server = make_server(state)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_investigation_progress",
            {},
        )

    assert not result.is_error

    data = result.structured_content
    assert data is not None
    assert data["collected_count"] == 1
    assert data["total_count"] == 2
    assert data["collection_rate"] == 50.0
    assert data["score"] == 2
    assert data["can_accuse"] is False


@pytest.mark.anyio
async def test_mcp_rejects_stale_context():
    state = make_state()
    server = make_server(state)

    state.revision += 1

    async with Client(server) as client:
        result = await client.call_tool("get_game_context", {})

    assert result.is_error
    assert result.structured_content is None


@pytest.mark.anyio
async def test_mcp_rejects_inconsistent_score():
    state = make_state(collected=("E01",))
    server = make_server(state)

    # 컨텍스트 생성 시점부터 잘못된 점수인 경우에도
    # Tool의 기존 진행률 검증에서 거부해야 합니다.
    state.score = 0

    async with Client(server) as client:
        result = await client.call_tool(
            "get_investigation_progress",
            {},
        )

    assert result.is_error
    assert result.structured_content is None


@pytest.mark.anyio
async def test_mcp_context_isolation_between_players():
    """서로 다른 MCP 인스턴스는 다른 세션의 정보를 반환하지 않습니다."""

    server_a = make_server(
        make_state("player-a", collected=("E01",))
    )
    server_b = make_server(
        make_state("player-b", collected=())
    )

    async def fetch(server):
        async with Client(server) as client:
            result = await client.call_tool("get_game_context", {})
            assert not result.is_error
            return result.structured_content

    result_a, result_b = await asyncio.gather(
        fetch(server_a),
        fetch(server_b),
    )

    assert result_a["collected_evidence_ids"] == ["E01"]
    assert result_b["collected_evidence_ids"] == []


@pytest.mark.anyio
async def test_mcp_read_only_execution():
    state = make_state(collected=("E01",))
    before = state.model_dump(mode="json")

    server = make_server(state)

    async with Client(server) as client:
        await client.call_tool("get_game_context", {})
        await client.call_tool("get_investigation_progress", {})

    assert state.model_dump(mode="json") == before

@pytest.mark.anyio
async def test_evidence_tool_requires_search_query():
    server = make_server(make_state())

    async with Client(server) as client:
        result = await client.call_tool(
            "search_authorized_evidence",
            {},
        )

    assert result.is_error
    assert result.structured_content is None