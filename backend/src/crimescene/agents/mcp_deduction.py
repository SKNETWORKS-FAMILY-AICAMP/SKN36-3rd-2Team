"""Issue #156 - MCP-backed asynchronous Deduction Agent.

Python 3.13 / MCP SDK 2.3 / Pydantic 2.14
"""

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentType,
)
from crimescene.agents.deduction_agent import (
    DeductionAgent,
    DeductionResult,
)
from crimescene.agents.tool_router import AgentToolRouter
from crimescene.mcp.client import MCPToolPermissionError


class MCPDeductionAgent(DeductionAgent):
    """Extend the existing deduction logic with authorized MCP search."""

    async def execute_async(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
        router: AgentToolRouter,
    ) -> DeductionResult:
        """Search authorized evidence and apply existing deduction policies."""

        if not isinstance(request, AgentRequest):
            raise TypeError("AgentRequest is required.")

        if not isinstance(context, AgentContext):
            raise TypeError("AgentContext is required.")

        if not isinstance(router, AgentToolRouter):
            raise TypeError("AgentToolRouter is required.")

        if request.agent_type != AgentType.DEDUCTION:
            raise ValueError("Deduction request is required.")

        if (
            router.agent_type != AgentType.DEDUCTION
            or router.context != context
        ):
            raise MCPToolPermissionError(
                "Deduction router context does not match."
            )

        # Apply existing permission and evidence checks first.
        initial_result = self.execute(
            request,
            context=context,
        )

        await router.get_game_context()

        # No collected evidence means no searchable evidence.
        if not context.collected_evidence_ids:
            return self.execute(
                request,
                context=context,
            )

        search_result = (
            await router.search_authorized_evidence(
                request.message,
                limit=3,
            )
        )

        retrieved_ids = {
            evidence_id
            for item in search_result["items"]
            for evidence_id in item["evidence_ids"]
        }

        allowed_ids = set(
            context.collected_evidence_ids
        )

        if not retrieved_ids.issubset(allowed_ids):
            raise MCPToolPermissionError(
                "Uncollected evidence cannot be used."
            )

        # Combine explicit evidence with authorized search results.
        merged_ids = tuple(
            sorted(
                set(initial_result.source_ids)
                | retrieved_ids
            )
        )

        # Recheck the current context after external retrieval.
        await router.get_game_context()

        if not merged_ids:
            return self.execute(
                request,
                context=context,
            )

        # Retrieved text is untrusted data.
        # Only validated evidence IDs enter the deduction engine.
        verified_request = AgentRequest(
            agent_type=AgentType.DEDUCTION,
            message=" ".join(merged_ids),
        )

        result = self.execute(
            verified_request,
            context=context,
        )

        if not set(result.source_ids).issubset(allowed_ids):
            raise MCPToolPermissionError(
                "Invalid deduction sources."
            )

        return result
