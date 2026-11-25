"""Issue #165 - reconstruction and give-up endpoints."""

from collections.abc import Callable

from fastapi import APIRouter, Cookie, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from crimescene.api.django_content_client import ContentServiceError
from crimescene.scenario.expanded_ending import (
    FINAL_FLAG,
    ExpandedCaseTruth,
    verify_reconstruction,
)
from crimescene.scenario.game_progress import (
    EXPANDED_EVIDENCE_IDS,
    meets_accusation_requirements,
)
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expectedRevision: int = Field(ge=0)


class ReconstructionRequest(RevisionRequest):
    selections: dict[str, list[str]] = Field(
        min_length=3,
        max_length=4,
    )


class ReconstructionResponse(BaseModel):
    accepted: bool
    created: bool
    revision: int


class GiveUpResponse(BaseModel):
    ending: str
    revision: int


def create_expanded_ending_router(
    *,
    repository: SQLiteCase001Repository,
    load_owned_request: Callable,
    stage_events: Callable[[GameState], GameState],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/games/{session_id}/reconstruction",
        response_model=ReconstructionResponse,
    )
    def reconstruct(
        session_id: str,
        body: ReconstructionRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> ReconstructionResponse:
        state = load_owned_request(
            session_id, request, case001_owner
        )

        if state.revision != body.expectedRevision:
            raise HTTPException(409, "Game state changed")

        truth = getattr(
            request.app.state,
            "case_truth",
            None,
        )

        if not isinstance(truth, ExpandedCaseTruth):
            raise HTTPException(503, "Reconstruction unavailable")

        try:
            updated = verify_reconstruction(
                state,
                selections=body.selections,
                truth=truth,
            )

        except PermissionError:
            raise HTTPException(403, "Reconstruction denied") from None

        except (ValueError, TypeError):
            raise HTTPException(422, "Invalid reconstruction") from None

        created = updated != state

        try:
            if created:
                updated = repository.commit_state(
                    expected_state=state,
                    updated_state=stage_events(updated),
                )

            elif repository.load_state(session_id) != state:
                raise ValueError("Game state changed")

        except ContentServiceError:
            raise HTTPException(503, "Story unavailable") from None

        except ValueError:
            raise HTTPException(409, "Game state changed") from None

        return ReconstructionResponse(
            accepted=FINAL_FLAG in updated.flags,
            created=created,
            revision=updated.revision,
        )

    @router.post(
        "/api/games/{session_id}/give-up",
        response_model=GiveUpResponse,
    )
    def give_up(
        session_id: str,
        body: RevisionRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> GiveUpResponse:
        state = load_owned_request(
            session_id, request, case001_owner
        )

        if (
            state.content_version != "case001_1120"
            or state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
            or state.attempts_left <= 0
            or state.revision != body.expectedRevision
        ):
            raise HTTPException(409, "Give-up unavailable")

        resources = getattr(
            request.app.state,
            "dialogue_resources",
            None,
        )

        rules = getattr(resources, "evidence_rules", None)

        if not rules or set(rules) != EXPANDED_EVIDENCE_IDS:
            raise HTTPException(503, "Evidence engine unavailable")

        try:
            sufficient = meets_accusation_requirements(
                state, rules
            )

            if sufficient:
                raise HTTPException(
                    409, "Accusation requirements already met"
                )

            updated = GameState.model_validate({
                **state.model_dump(),
                "phase": GamePhase.FINISHED,
                "outcome": "FAILURE",
                "ending_code": "NO_EVIDENCE",
                "deep_eligible": False,
                "revision": state.revision + 1,
            })

            committed = repository.commit_state(
                expected_state=state,
                updated_state=updated,
            )

        except (TypeError, ValueError):
            raise HTTPException(409, "Game state changed") from None

        return GiveUpResponse(
            ending="NO_EVIDENCE",
            revision=committed.revision,
        )

    return router
