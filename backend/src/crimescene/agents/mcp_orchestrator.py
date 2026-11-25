"""Issue #156 - Asynchronous MCP Multi-Agent orchestration."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from mcp.server import MCPServer
from pydantic import BaseModel, ConfigDict

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentResult,
    AgentType,
)
from crimescene.agents.deduction_agent import (
    DeductionResult,
    DeductionStatus,
)
from crimescene.agents.hint_agent import (
    HintResult,
    parse_hint_level,
)
from crimescene.agents.mcp_deduction import MCPDeductionAgent
from crimescene.agents.mcp_hint import MCPHintAgent
from crimescene.agents.orchestrator import AgentExecutionTimeout
from crimescene.agents.tool_router import AgentToolRouter
from crimescene.mcp.client import (
    MCPToolPermissionError,
    MCPToolTimeoutError,
    MCPToolValidationError,
)
from crimescene.mcp.context import BoundMCPContext
from crimescene.scenario.evidence_collection import VALID_STAGES
from crimescene.scenario.game_progress import CASE_ID
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)

WORKFLOW_TIMEOUT_SECONDS = 60.0

SUPPORTED_AGENTS = frozenset({
    AgentType.DEDUCTION,
    AgentType.HINT,
})


class AgentCollaborationResult(BaseModel):
    """Validated results from one read-only collaboration."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    deduction: DeductionResult
    hint: HintResult


class MCPAgentOrchestrator:
    """Coordinate agents within one authenticated game context.

    Session ownership must be verified by the calling API.
    The server factory must use the provided bound context.
    """

    def __init__(
        self,
        *,
        deduction_agent: MCPDeductionAgent,
        hint_agent: MCPHintAgent,
        load_state: Callable[[str], GameState],
        server_factory: Callable[
            [BoundMCPContext], MCPServer
        ],
    ) -> None:
        if not isinstance(
            deduction_agent,
            MCPDeductionAgent,
        ):
            raise TypeError("MCPDeductionAgent is required.")

        if not isinstance(hint_agent, MCPHintAgent):
            raise TypeError("MCPHintAgent is required.")

        if not callable(load_state):
            raise TypeError("State loader is required.")

        if not callable(server_factory):
            raise TypeError("Server factory is required.")

        self._deduction_agent = deduction_agent
        self._hint_agent = hint_agent
        self._load_state = load_state
        self._server_factory = server_factory

    def _get_state(self, session_id: str) -> GameState:
        state = self._load_state(session_id)

        if not isinstance(state, GameState):
            raise TypeError("Invalid GameState.")

        if (
            state.session_id != session_id
            or state.case_id != CASE_ID
        ):
            raise PermissionError(
                "Game session or case does not match."
            )

        return state

    def _validate_context(
        self,
        context: AgentContext,
    ) -> GameState:
        if not isinstance(context, AgentContext):
            raise TypeError("AgentContext is required.")

        state = self._get_state(context.session_id)

        expected = AgentContext.from_game_state(
            state,
            active_character_id=(
                context.active_character_id
            ),
        )

        if expected != context:
            raise RuntimeError(
                "Game context is no longer current."
            )

        if (
            state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
        ):
            raise PermissionError(
                "Investigation phase is required."
            )

        if any(
            item.stage not in VALID_STAGES
            for item in state.evidence.values()
        ):
            raise PermissionError(
                "Invalid evidence collection state."
            )

        return state

    @staticmethod
    def _validate_request(
        request: AgentRequest,
        expected: AgentType | None = None,
    ) -> None:
        if not isinstance(request, AgentRequest):
            raise TypeError("AgentRequest is required.")

        if request.agent_type not in SUPPORTED_AGENTS:
            raise MCPToolPermissionError(
                "Agent is not supported by this workflow."
            )

        if (
            expected is not None
            and request.agent_type != expected
        ):
            raise ValueError("Agent type does not match.")

        if request.presented_evidence_id is not None:
            raise MCPToolPermissionError(
                "Evidence presentation is not permitted."
            )

    @staticmethod
    def _validate_result(
        result: AgentResult,
        *,
        context: AgentContext,
        expected: AgentType,
    ) -> None:
        if not isinstance(result, AgentResult):
            raise TypeError("AgentResult is required.")

        if result.agent_type != expected:
            raise MCPToolValidationError(
                "Agent response type does not match."
            )

        if not set(result.source_ids).issubset(
            context.collected_evidence_ids
        ):
            raise MCPToolPermissionError(
                "Uncollected evidence in agent result."
            )

    @asynccontextmanager
    async def _execution_scope(
        self,
        context: AgentContext,
    ) -> AsyncIterator[MCPServer]:
        """Bind a single server to the verified snapshot."""

        state = self._validate_context(context)

        original = state.model_dump(mode="json")

        try:
            async with asyncio.timeout(
                WORKFLOW_TIMEOUT_SECONDS
            ):
                bound = (
                    BoundMCPContext.from_owned_game_state(
                        state=state,
                        load_state=self._load_state,
                        active_character_id=(
                            context.active_character_id
                        ),
                    )
                )

                server = self._server_factory(bound)

                if not isinstance(server, MCPServer):
                    raise TypeError(
                        "Invalid MCP server."
                    )

                yield server

        except (TimeoutError, MCPToolTimeoutError):
            raise AgentExecutionTimeout(
                "Agent workflow timed out."
            ) from None

        finally:
            # Never return results from a changed game state.
            current = self._get_state(context.session_id)

            if current.model_dump(mode="json") != original:
                raise RuntimeError(
                    "Game state changed during agent workflow."
                )

    async def _run_deduction(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
        server: MCPServer,
    ) -> DeductionResult:
        router = AgentToolRouter(
            agent_type=AgentType.DEDUCTION,
            context=context,
            server=server,
        )

        result = await self._deduction_agent.execute_async(
            request,
            context=context,
            router=router,
        )

        if not isinstance(result, DeductionResult):
            raise TypeError("DeductionResult is required.")

        self._validate_result(
            result,
            context=context,
            expected=AgentType.DEDUCTION,
        )

        if bool(result.source_ids) != (
            result.status
            == DeductionStatus.RELATED_EVIDENCE
        ):
            raise MCPToolValidationError(
                "Invalid deduction status."
            )

        return result

    async def _run_hint(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
        server: MCPServer,
        deduction_result: DeductionResult | None = None,
    ) -> HintResult:
        router = AgentToolRouter(
            agent_type=AgentType.HINT,
            context=context,
            server=server,
        )

        result = await self._hint_agent.execute_async(
            request,
            context=context,
            router=router,
            deduction_result=deduction_result,
        )

        if not isinstance(result, HintResult):
            raise TypeError("HintResult is required.")

        self._validate_result(
            result,
            context=context,
            expected=AgentType.HINT,
        )

        if (
            result.chapter != context.current_chapter
            or result.collected_count
            != len(context.collected_evidence_ids)
            or result.level
            != parse_hint_level(request.message)
        ):
            raise MCPToolValidationError(
                "Hint result does not match the context."
            )

        character_id = result.suggested_character_id

        if (
            character_id is not None
            and character_id not in context.unlocked_characters
        ):
            raise MCPToolPermissionError(
                "Locked character in hint result."
            )

        if result.level == 1 and (
            result.source_ids or character_id is not None
        ):
            raise MCPToolPermissionError(
                "Level one hint exposes additional evidence."
            )

        if (
            deduction_result is not None
            and deduction_result.source_ids
            and not set(result.source_ids).issubset(
                deduction_result.source_ids
            )
        ):
            raise MCPToolPermissionError(
                "Hint exceeds the verified deduction sources."
            )

        return result

    async def execute_async(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
    ) -> DeductionResult | HintResult:
        """Execute one read-only MCP agent."""

        self._validate_request(request)

        if request.agent_type == AgentType.HINT:
            parse_hint_level(request.message)

        async with self._execution_scope(context) as server:
            if request.agent_type == AgentType.DEDUCTION:
                return await self._run_deduction(
                    request,
                    context=context,
                    server=server,
                )

            return await self._run_hint(
                request,
                context=context,
                server=server,
            )

    async def assist(
        self,
        deduction_request: AgentRequest,
        hint_request: AgentRequest,
        *,
        context: AgentContext,
    ) -> AgentCollaborationResult:
        """Run Deduction followed by Hint in one execution scope."""

        self._validate_request(
            deduction_request,
            AgentType.DEDUCTION,
        )

        self._validate_request(
            hint_request,
            AgentType.HINT,
        )

        # Validate both requests before retrieval.
        parse_hint_level(hint_request.message)

        async with self._execution_scope(context) as server:
            deduction = await self._run_deduction(
                deduction_request,
                context=context,
                server=server,
            )

            # Revalidate the shared snapshot before handoff.
            self._validate_context(context)

            hint = await self._run_hint(
                hint_request,
                context=context,
                server=server,
                deduction_result=deduction,
            )

            return AgentCollaborationResult(
                deduction=deduction,
                hint=hint,
            )
