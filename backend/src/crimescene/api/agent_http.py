"""Issue #157 - Authenticated read-only Multi-Agent HTTP API."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentType,
)
from crimescene.agents.deduction_agent import DeductionResult
from crimescene.agents.hint_agent import HintResult
from crimescene.agents.mcp_deduction import MCPDeductionAgent
from crimescene.agents.mcp_hint import MCPHintAgent
from crimescene.agents.mcp_orchestrator import (
    AgentCollaborationResult,
    MCPAgentOrchestrator,
)
from crimescene.agents.orchestrator import AgentExecutionTimeout
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.mcp.client import (
    MCPToolError,
    MCPToolPermissionError,
    MCPToolTimeoutError,
    MCPToolValidationError,
)
from crimescene.mcp.context import BoundMCPContext
from crimescene.mcp.server import create_readonly_mcp_server
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

LoadOwnedRequest = Callable[
    [str, Request, str | None],
    GameState,
]

AgentMessage = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
    ),
]

STATE_CONFLICT_MESSAGES = frozenset({
    "Game context is no longer current.",
    "Game state changed during agent workflow.",
    ("\uac8c\uc784 \uc0c1\ud0dc \uc2a4\ub0c5\uc0f7\uc774 "
    "\ubcc0\uacbd\ub410\uc2b5\ub2c8\ub2e4."),
})


# Request schemas


class AgentHTTPInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )

    expectedRevision: int = Field(ge=0)


class DeductionRequest(AgentHTTPInput):
    message: AgentMessage


class HintRequest(AgentHTTPInput):
    level: int = Field(default=1, ge=1, le=3)


class AssistRequest(AgentHTTPInput):
    message: AgentMessage
    level: int = Field(default=2, ge=1, le=3)


# Public response schemas


class DeductionResponse(BaseModel):
    agentType: str
    text: str
    sourceIds: list[str]
    status: str
    verdict: str
    contradiction: str
    revision: int


class HintResponse(BaseModel):
    agentType: str
    text: str
    sourceIds: list[str]
    level: int
    status: str
    chapter: str
    collectedCount: int
    suggestedCharacterId: str | None
    revision: int


class AssistResponse(BaseModel):
    deduction: DeductionResponse
    hint: HintResponse
    revision: int


def deduction_response(
    result: DeductionResult,
    revision: int,
) -> DeductionResponse:
    return DeductionResponse(
        agentType=result.agent_type.value,
        text=result.text,
        sourceIds=list(result.source_ids),
        status=result.status.value,
        verdict=result.verdict,
        contradiction=result.contradiction,
        revision=revision,
    )


def hint_response(
    result: HintResult,
    revision: int,
) -> HintResponse:
    return HintResponse(
        agentType=result.agent_type.value,
        text=result.text,
        sourceIds=list(result.source_ids),
        level=result.level,
        status=result.status.value,
        chapter=result.chapter,
        collectedCount=result.collected_count,
        suggestedCharacterId=result.suggested_character_id,
        revision=revision,
    )


def create_agent_router(
    *,
    repository: SQLiteCase001Repository,
    load_owned_request: LoadOwnedRequest,
    dialogue_resources: NPCRAGResources | None = None,
) -> APIRouter:
    """Register authenticated, read-only agent endpoints."""

    router = APIRouter(
        prefix="/api/games/{session_id}/agents",
        tags=["Agents"],
    )

    def build_runtime(
        session_id: str,
        request: Request,
        cookie: str | None,
        expected_revision: int,
    ) -> tuple[AgentContext, MCPAgentOrchestrator]:

        # Authenticate before accessing runtime resources.
        state = load_owned_request(
            session_id,
            request,
            cookie,
        )

        if state.revision != expected_revision:
            raise HTTPException(
                status_code=409,
                detail="Game revision does not match.",
            )

        if (
            state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
        ):
            raise HTTPException(
                status_code=409,
                detail="Investigation phase is required.",
            )

        resources = getattr(
            request.app.state,
            "dialogue_resources",
            dialogue_resources,
        )

        django_client = getattr(
            request.app.state,
            "django_content_client",
            None,
        )

        if (
            not isinstance(resources, NPCRAGResources)
            or not resources.evidence_rules
        ):
            raise HTTPException(
                status_code=503,
                detail="Agent resources are unavailable.",
            )

        if not isinstance(
            django_client,
            DjangoContentClient,
        ):
            raise HTTPException(
                status_code=503,
                detail="Content service is unavailable.",
            )

        if resources.content_version != state.content_version:
            raise HTTPException(
                status_code=503,
                detail="Agent content version mismatch.",
            )

        context = AgentContext.from_game_state(state)

        version_options = (
            {"content_version": state.content_version}
            if state.content_version != "case001_v7_1"
            else {}
        )

        def server_factory(bound: BoundMCPContext):
            return create_readonly_mcp_server(
                context=bound,
                evidence_rules=resources.evidence_rules,
                evaluator=resources.evaluator,
                django_client=django_client,
                rag_resources=resources,
            )

        # Do not expose local document or graph metadata
        # independently of the MCP approval boundary.
        deduction = MCPDeductionAgent(
            load_state=repository.load_state,
            evidence_rules=resources.evidence_rules,
            **version_options,
        )

        hint = MCPHintAgent(
            load_state=repository.load_state,
            evidence_rules=resources.evidence_rules,
            **version_options,
        )

        workflow = MCPAgentOrchestrator(
            deduction_agent=deduction,
            hint_agent=hint,
            load_state=repository.load_state,
            server_factory=server_factory,
        )

        return context, workflow

    async def execute_workflow(
        *,
        session_id: str,
        request: Request,
        cookie: str | None,
        expected_revision: int,
        agent_request: AgentRequest,
        collaboration_hint: AgentRequest | None = None,
    ) -> tuple[
        DeductionResult | HintResult | AgentCollaborationResult,
        int,
    ]:
        """Execute an authenticated workflow and sanitize errors."""

        try:
            context, workflow = build_runtime(
                session_id,
                request,
                cookie,
                expected_revision,
            )

            if collaboration_hint is not None:
                result = await workflow.assist(
                    agent_request,
                    collaboration_hint,
                    context=context,
                )
            else:
                result = await workflow.execute_async(
                    agent_request,
                    context=context,
                )

            return result, context.revision

        except (AgentExecutionTimeout, MCPToolTimeoutError):
            raise HTTPException(
                status_code=504,
                detail="Agent execution timed out.",
            ) from None

        except (MCPToolPermissionError, PermissionError):
            raise HTTPException(
                status_code=403,
                detail="Agent access is not permitted.",
            ) from None

        except MCPToolValidationError:
            raise HTTPException(
                status_code=502,
                detail="Invalid agent tool response.",
            ) from None

        except MCPToolError:
            raise HTTPException(
                status_code=503,
                detail="Agent tool service is unavailable.",
            ) from None

        except RuntimeError as exc:
            if str(exc) in STATE_CONFLICT_MESSAGES:
                raise HTTPException(
                    status_code=409,
                    detail="Game state changed during execution.",
                ) from None

            raise HTTPException(
                status_code=503,
                detail="Agent service is unavailable.",
            ) from None

        except (TypeError, ValueError, OSError):
            raise HTTPException(
                status_code=503,
                detail="Agent service is unavailable.",
            ) from None

    @router.post(
        "/deduction",
        response_model=DeductionResponse,
    )
    async def execute_deduction(
        session_id: str,
        body: DeductionRequest,
        request: Request,
        response: Response,
        case001_owner: str | None = Cookie(default=None),
    ) -> DeductionResponse:

        result, revision = await execute_workflow(
            session_id=session_id,
            request=request,
            cookie=case001_owner,
            expected_revision=body.expectedRevision,
            agent_request=AgentRequest(
                agent_type=AgentType.DEDUCTION,
                message=body.message,
            ),
        )

        if not isinstance(result, DeductionResult):
            raise HTTPException(
                status_code=502,
                detail="Invalid deduction result.",
            )

        response.headers["Cache-Control"] = "no-store"

        return deduction_response(result, revision)

    @router.post(
        "/hint",
        response_model=HintResponse,
    )
    async def execute_hint(
        session_id: str,
        body: HintRequest,
        request: Request,
        response: Response,
        case001_owner: str | None = Cookie(default=None),
    ) -> HintResponse:

        result, revision = await execute_workflow(
            session_id=session_id,
            request=request,
            cookie=case001_owner,
            expected_revision=body.expectedRevision,
            agent_request=AgentRequest(
                agent_type=AgentType.HINT,
                message=f"{body.level}\uB2E8\uACC4",
            ),
        )

        if not isinstance(result, HintResult):
            raise HTTPException(
                status_code=502,
                detail="Invalid hint result.",
            )

        response.headers["Cache-Control"] = "no-store"

        return hint_response(result, revision)

    @router.post(
        "/assist",
        response_model=AssistResponse,
    )
    async def execute_assist(
        session_id: str,
        body: AssistRequest,
        request: Request,
        response: Response,
        case001_owner: str | None = Cookie(default=None),
    ) -> AssistResponse:

        result, revision = await execute_workflow(
            session_id=session_id,
            request=request,
            cookie=case001_owner,
            expected_revision=body.expectedRevision,
            agent_request=AgentRequest(
                agent_type=AgentType.DEDUCTION,
                message=body.message,
            ),
            collaboration_hint=AgentRequest(
                agent_type=AgentType.HINT,
                message=f"{body.level}\uB2E8\uACC4",
            ),
        )

        if not isinstance(
            result,
            AgentCollaborationResult,
        ):
            raise HTTPException(
                status_code=502,
                detail="Invalid collaboration result.",
            )

        response.headers["Cache-Control"] = "no-store"

        return AssistResponse(
            deduction=deduction_response(
                result.deduction,
                revision,
            ),
            hint=hint_response(
                result.hint,
                revision,
            ),
            revision=revision,
        )

    return router
