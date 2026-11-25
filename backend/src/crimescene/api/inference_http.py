"""Issue #165 - owner-scoped objective and inference API."""

from collections.abc import Callable

from fastapi import APIRouter, Cookie, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from crimescene.api.django_content_client import (
    ContentServiceError,
)
from crimescene.scenario.investigation_progress import (
    InferenceRule,
    ObjectiveRule,
    objective_status,
    submit_inference,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


class InferenceRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    evidenceIds: list[str] = Field(
        min_length=2,
        max_length=3,
    )

    expectedRevision: int = Field(ge=0)


class InferenceResponse(BaseModel):
    accepted: bool
    created: bool
    inferenceIds: list[str]
    revision: int


class ObjectiveItem(BaseModel):
    objectiveId: str
    status: str


class ObjectiveResponse(BaseModel):
    items: list[ObjectiveItem]


def create_inference_router(
    *,
    repository: SQLiteCase001Repository,
    load_owned_request: Callable,
    stage_events: Callable[[GameState], GameState],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/games/{session_id}/objectives",
        response_model=ObjectiveResponse,
    )
    def list_objectives(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> ObjectiveResponse:
        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        rules = getattr(
            request.app.state,
            "approved_objective_rules",
            (),
        )

        if (
            not isinstance(rules, tuple)
            or any(
                not isinstance(rule, ObjectiveRule)
                for rule in rules
            )
        ):
            raise HTTPException(503, "Objectives unavailable")

        items = []

        for rule in rules:
            status = objective_status(state, rule)

            if status == "LOCKED":
                continue

            items.append(
                ObjectiveItem(
                    objectiveId=rule.objective_id,
                    status=status,
                )
            )

        return ObjectiveResponse(items=items)

    @router.post(
        "/api/games/{session_id}/inferences",
        response_model=InferenceResponse,
    )
    def infer(
        session_id: str,
        body: InferenceRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> InferenceResponse:
        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if state.revision != body.expectedRevision:
            raise HTTPException(409, "Game state changed")

        ids = frozenset(body.evidenceIds)

        if len(ids) != len(body.evidenceIds):
            raise HTTPException(422, "Duplicate evidence ID")

        rules = getattr(
            request.app.state,
            "approved_inference_rules",
            (),
        )

        if (
            not isinstance(rules, tuple)
            or any(
                not isinstance(rule, InferenceRule)
                for rule in rules
            )
        ):
            raise HTTPException(503, "Inference unavailable")

        try:
            result = submit_inference(
                state,
                evidence_ids=ids,
                rules=rules,
                **(
                    {
                        "e26_section_a_approved": getattr(
                            request.app.state,
                            "e26_section_a_approved",
                            False,
                        )
                    }
                    if "E26" in ids
                    else {}
                ),
            )

        except PermissionError:
            raise HTTPException(403, "Inference denied") from None

        except (TypeError, ValueError):
            raise HTTPException(422, "Invalid inference") from None

        committed = state

        try:
            if result.created:
                updated = stage_events(result.state)

                committed = repository.commit_state(
                    expected_state=state,
                    updated_state=updated,
                )

            elif repository.load_state(session_id) != state:
                raise ValueError("Game state changed")

        except ContentServiceError:
            raise HTTPException(
                503, "Story approval unavailable"
            ) from None

        except ValueError:
            raise HTTPException(
                409, "Game state changed"
            ) from None

        return InferenceResponse(
            accepted=result.accepted,
            created=result.created,
            inferenceIds=list(result.inference_ids),
            revision=committed.revision,
        )

    return router
