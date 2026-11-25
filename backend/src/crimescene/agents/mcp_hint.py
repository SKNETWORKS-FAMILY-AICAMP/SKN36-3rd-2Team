"""Issue #156 - MCP-backed asynchronous Hint Agent.

Python 3.13 / MCP SDK 2.3 / Pydantic 2.14
"""

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentType,
)
from crimescene.agents.deduction_agent import (
    DeductionResult,
    DeductionStatus,
)
from crimescene.agents.hint_agent import (
    HintAgent,
    HintResult,
)
from crimescene.agents.tool_router import AgentToolRouter
from crimescene.mcp.client import (
    MCPToolPermissionError,
    MCPToolValidationError,
)


class MCPHintAgent(HintAgent):
    """Generate hints from verified MCP state and deduction sources."""

    async def execute_async(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
        router: AgentToolRouter,
        deduction_result: DeductionResult | None = None,
    ) -> HintResult:
        """Generate a read-only hint with optional agent collaboration."""

        if not isinstance(request, AgentRequest):
            raise TypeError("AgentRequest is required.")

        if not isinstance(context, AgentContext):
            raise TypeError("AgentContext is required.")

        if not isinstance(router, AgentToolRouter):
            raise TypeError("AgentToolRouter is required.")

        if request.agent_type != AgentType.HINT:
            raise ValueError("Hint request is required.")

        if (
            router.agent_type != AgentType.HINT
            or router.context != context
        ):
            raise MCPToolPermissionError(
                "Hint router context does not match."
            )

        # Validate the original hint request and server state.
        self.execute(
            request,
            context=context,
        )

        allowed_ids = set(
            context.collected_evidence_ids
        )

        preferred_ids: tuple[str, ...] = ()

        if deduction_result is not None:
            if not isinstance(
                deduction_result,
                DeductionResult,
            ):
                raise TypeError(
                    "DeductionResult is required."
                )

            if deduction_result.agent_type != AgentType.DEDUCTION:
                raise MCPToolValidationError(
                    "Invalid deduction agent type."
                )

            preferred_ids = tuple(
                sorted(set(deduction_result.source_ids))
            )

            if not set(preferred_ids).issubset(allowed_ids):
                raise MCPToolPermissionError(
                    "Uncollected deduction sources."
                )

            if (
                bool(preferred_ids)
                != (
                    deduction_result.status
                    == DeductionStatus.RELATED_EVIDENCE
                )
            ):
                raise MCPToolValidationError(
                    "Invalid deduction source status."
                )

        # Read current state and progress through the real MCP client.
        await router.get_game_context()

        progress = (
            await router.get_investigation_progress()
        )

        # Reject stale state before constructing the final hint.
        await router.get_game_context()

        baseline = self.execute(
            request,
            context=context,
        )

        if (
            progress["collected_count"]
            != baseline.collected_count
            or progress["current_chapter"]
            != baseline.chapter
        ):
            raise MCPToolValidationError(
                "Hint progress does not match."
            )

        # Level 1 never reveals additional evidence.
        if baseline.level == 1:
            return baseline.model_copy(
                update={
                    "text": (
                        f"{baseline.text} "
                        f"Currently collected evidence: "
                        f"{progress['collected_count']}."
                    ),
                }
            )

        # Preserve the original rules without deduction sources.
        if not preferred_ids:
            return baseline

        # Level 2 prioritizes the evidence found by Deduction Agent.
        if baseline.level == 2:
            selected = preferred_ids[:2]
            sources = ", ".join(selected)

            return baseline.model_copy(
                update={
                    "text": (
                        f"Review collected evidence: {sources}. "
                        "Compare recorded people, times, "
                        "and verifiable facts."
                    ),
                    "source_ids": selected,
                }
            )

        # Level 3 recommends only already unlocked characters.
        unlocked = set(
            context.unlocked_characters
        )

        if not unlocked:
            return baseline

        selected_id = preferred_ids[0]

        holder = self._rules[selected_id].holder

        character_id = (
            holder
            if holder in unlocked
            else min(unlocked)
        )

        return baseline.model_copy(
            update={
                "text": (
                    f"Ask unlocked character {character_id} "
                    f"about collected evidence {selected_id}. "
                    "Compare the response with public records."
                ),
                "source_ids": (selected_id,),
                "suggested_character_id": character_id,
            }
        )
