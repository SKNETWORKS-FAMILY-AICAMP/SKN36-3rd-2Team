"""Issue #156 - Agent-specific MCP tool routing.

Python 3.13 / MCP SDK 2.3 / Pydantic 2.14
"""

from types import MappingProxyType
from typing import cast

from mcp.server import MCPServer

from crimescene.agents.contracts import AgentContext, AgentType
from crimescene.mcp.client import (
    MCPToolClient,
    MCPToolPermissionError,
    MCPToolValidationError,
)
from crimescene.mcp.evidence_tools import EvidenceSearchPayload
from crimescene.mcp.server import (
    GameContextPayload,
    InvestigationProgressPayload,
)
from crimescene.scenario.schemas.game_state import GamePhase

AGENT_TOOL_ALLOWLIST = MappingProxyType({
    AgentType.DEDUCTION: frozenset({
        "get_game_context",
        "get_investigation_progress",
        "search_authorized_evidence",
    }),
    AgentType.HINT: frozenset({
        "get_game_context",
        "get_investigation_progress",
    }),
})


def get_allowed_tools(
    agent_type: AgentType,
) -> frozenset[str]:
    """Return the immutable server-side tool policy."""

    if not isinstance(agent_type, AgentType):
        raise TypeError("AgentType is required.")

    if agent_type not in AGENT_TOOL_ALLOWLIST:
        raise MCPToolPermissionError(
            "MCP routing is not enabled for this agent."
        )

    return AGENT_TOOL_ALLOWLIST[agent_type]


class AgentToolRouter:
    """Read-only MCP tools scoped to one agent and context.

    The server and context must originate from the same
    authenticated game state. This router does not replace
    session ownership authentication.
    """

    def __init__(
        self,
        *,
        agent_type: AgentType,
        context: AgentContext,
        server: MCPServer,
        timeout_seconds: float = 15.0,
    ) -> None:
        allowed_tools = get_allowed_tools(agent_type)

        if not isinstance(context, AgentContext):
            raise TypeError("AgentContext is required.")

        if context.phase != GamePhase.INVESTIGATION:
            raise MCPToolPermissionError(
                "Agent tools require the investigation phase."
            )

        self._agent_type = agent_type
        self._context = context

        self._client = MCPToolClient(
            server=server,
            allowed_tools=allowed_tools,
            timeout_seconds=timeout_seconds,
        )

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    @property
    def context(self) -> AgentContext:
        return self._context

    @property
    def allowed_tools(self) -> frozenset[str]:
        return self._client.allowed_tools

    async def get_game_context(
        self,
    ) -> GameContextPayload:
        """Verify MCP state against the agent snapshot."""

        payload = cast(
            GameContextPayload,
            await self._client.call_tool(
                "get_game_context"
            ),
        )

        context = self._context

        if (
            payload["revision"] != context.revision
            or payload["phase"] != context.phase.value
            or payload["current_chapter"]
            != context.current_chapter
            or tuple(
                sorted(payload["collected_evidence_ids"])
            ) != context.collected_evidence_ids
            or tuple(
                sorted(payload["unlocked_character_ids"])
            ) != context.unlocked_characters
        ):
            raise MCPToolValidationError(
                "MCP context does not match the agent context."
            )

        return payload

    async def get_investigation_progress(
        self,
    ) -> InvestigationProgressPayload:
        """Return validated investigation progress."""

        payload = cast(
            InvestigationProgressPayload,
            await self._client.call_tool(
                "get_investigation_progress"
            ),
        )

        if (
            payload["current_chapter"]
            != self._context.current_chapter
            or payload["collected_count"]
            != len(self._context.collected_evidence_ids)
            or not (
                0 <= payload["collected_count"]
                <= payload["total_count"]
            )
            or not (
                0 <= payload["collection_rate"] <= 100
            )
            or not (
                0 <= payload["score"]
                <= payload["total_score"]
            )
        ):
            raise MCPToolValidationError(
                "Invalid investigation progress."
            )

        return payload

    async def search_authorized_evidence(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> EvidenceSearchPayload:
        """Search evidence without expanding access rights."""

        payload = cast(
            EvidenceSearchPayload,
            await self._client.call_tool(
                "search_authorized_evidence",
                {
                    "query": query,
                    "limit": limit,
                },
            ),
        )

        allowed_ids = set(
            self._context.collected_evidence_ids
        )

        if len(payload["items"]) > limit:
            raise MCPToolValidationError(
                "Evidence search result limit exceeded."
            )

        seen_documents: set[str] = set()

        for item in payload["items"]:
            evidence_ids = item["evidence_ids"]

            # Never accept evidence outside the trusted snapshot.
            if (
                not evidence_ids
                or not set(evidence_ids).issubset(
                    allowed_ids
                )
            ):
                raise MCPToolPermissionError(
                    "Uncollected evidence in search results."
                )

            if (
                not item["document_id"].strip()
                or not item["title"].strip()
                or not item["excerpt"].strip()
                or item["document_id"] in seen_documents
            ):
                raise MCPToolValidationError(
                    "Invalid evidence search result."
                )

            seen_documents.add(item["document_id"])

        # Retrieved text is untrusted data, not instructions.
        return payload
