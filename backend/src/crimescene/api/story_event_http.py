"""Owner-scoped HTTP endpoints for approved story events."""

import re
from collections.abc import Callable, Mapping

from fastapi import APIRouter, Cookie, HTTPException, Request
from pydantic import BaseModel

from crimescene.api.django_content_client import (
    ContentServiceError,
    ContentServiceNotFoundError,
)
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.api.story_event_delivery_service import (
    acknowledge_story_event_atomic,
    get_pending_story_event,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

EVENT_KEY_PATTERN = re.compile(r"EVT-CH0[0-4]-[0-9]{3}")

LoadOwnedRequest = Callable[
    [str, Request, str | None],
    GameState,
]


class PendingStoryEventResponse(BaseModel):
    eventKey: str
    chapter: str
    title: str
    text: str


class PendingStoryEventsResponse(BaseModel):
    items: list[PendingStoryEventResponse]


class StoryEventAckResponse(BaseModel):
    eventKey: str
    acknowledged: bool
    created: bool
    revision: int


def create_story_event_router(
    *,
    repository: SQLiteCase001Repository,
    load_owned_request: LoadOwnedRequest,
) -> APIRouter:
    """Attach routes without weakening existing session ownership."""

    router = APIRouter()

    def require_binding(
        request: Request,
        event_key: str,
    ) -> StoryEventBinding:
        if not EVENT_KEY_PATTERN.fullmatch(event_key):
            raise HTTPException(status_code=404, detail="Event not found")

        # No bindings are enabled by default.
        bindings = getattr(
            request.app.state,
            "story_event_bindings",
            None,
        )

        if not isinstance(bindings, Mapping):
            raise HTTPException(status_code=404, detail="Event not found")

        binding = bindings.get(event_key)

        if not isinstance(binding, StoryEventBinding) or binding.event_key != event_key:
            raise HTTPException(status_code=404, detail="Event not found")

        return binding

    def approved_fetcher(request: Request):
        client = getattr(
            request.app.state,
            "django_content_client",
            None,
        )

        if client is None or not callable(
            getattr(client, "get_approved_story_event", None)
        ):
            raise HTTPException(
                status_code=503,
                detail="Content service unavailable",
            )

        def fetch(event_key: str):
            return client.get_approved_story_event(
                "CASE-001",
                event_key,
            )

        return fetch

    @router.get(
        "/api/games/{session_id}/story-events/pending",
        response_model=PendingStoryEventsResponse,
    )
    def list_pending_story_events(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> PendingStoryEventsResponse:
        """List only approved, queued, unacknowledged events."""

        load_owned_request(session_id, request, case001_owner)

        bindings = getattr(
            request.app.state,
            "story_event_bindings",
            None,
        )

        # No approved runtime registry: expose nothing.
        if bindings is None:
            return PendingStoryEventsResponse(items=[])

        if not isinstance(bindings, Mapping) or len(bindings) > 30:
            raise HTTPException(
                status_code=503,
                detail="Story event configuration unavailable",
            )

        verified_bindings = []

        for event_key, binding in bindings.items():
            if (
                not isinstance(event_key, str)
                or not EVENT_KEY_PATTERN.fullmatch(event_key)
                or not isinstance(binding, StoryEventBinding)
                or binding.event_key != event_key
            ):
                raise HTTPException(
                    status_code=503,
                    detail="Story event configuration unavailable",
                )

            verified_bindings.append(binding)

        if not verified_bindings:
            return PendingStoryEventsResponse(items=[])

        fetch = approved_fetcher(request)
        items = []

        try:
            for binding in sorted(
                verified_bindings,
                key=lambda item: item.event_key,
            ):
                try:
                    event = get_pending_story_event(
                        repository,
                        session_id,
                        binding,
                        fetch,
                    )
                except ContentServiceNotFoundError:
                    # Unpublished or unapproved content remains hidden.
                    continue

                if event is None:
                    continue

                items.append(
                    PendingStoryEventResponse(
                        eventKey=event.event_key,
                        chapter=event.chapter,
                        title=event.title,
                        text=event.text,
                    )
                )

        except ContentServiceError:
            # Never return a partial list if Django fails midway.
            raise HTTPException(
                status_code=503,
                detail="Content service unavailable",
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409,
                detail="Game state changed",
            ) from None

        return PendingStoryEventsResponse(items=items)

    @router.get(
        "/api/games/{session_id}/story-events/{event_key}",
        response_model=PendingStoryEventResponse,
    )
    def get_story_event(
        session_id: str,
        event_key: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> PendingStoryEventResponse:
        # Ownership must be checked before looking up event metadata.
        load_owned_request(session_id, request, case001_owner)

        binding = require_binding(request, event_key)
        fetch = approved_fetcher(request)

        try:
            event = get_pending_story_event(
                repository,
                session_id,
                binding,
                fetch,
            )
        except ContentServiceNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="Event not found",
            ) from None
        except ContentServiceError:
            raise HTTPException(
                status_code=503,
                detail="Content service unavailable",
            ) from None

        if event is None:
            raise HTTPException(
                status_code=404,
                detail="Event not found",
            )

        return PendingStoryEventResponse(
            eventKey=event.event_key,
            chapter=event.chapter,
            title=event.title,
            text=event.text,
        )

    @router.post(
        "/api/games/{session_id}/story-events/{event_key}/ack",
        response_model=StoryEventAckResponse,
    )
    def acknowledge_story_event(
        session_id: str,
        event_key: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> StoryEventAckResponse:
        load_owned_request(session_id, request, case001_owner)

        binding = require_binding(request, event_key)
        fetch = approved_fetcher(request)

        try:
            result = acknowledge_story_event_atomic(
                repository,
                session_id,
                binding,
                fetch,
            )
        except (ContentServiceNotFoundError, PermissionError):
            raise HTTPException(
                status_code=404,
                detail="Event not found",
            ) from None
        except ContentServiceError:
            raise HTTPException(
                status_code=503,
                detail="Content service unavailable",
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409,
                detail="Game state changed",
            ) from None

        return StoryEventAckResponse(
            eventKey=event_key,
            acknowledged=True,
            created=result.created,
            revision=result.state.revision,
        )

    return router
