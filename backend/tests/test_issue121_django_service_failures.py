"""Issue #121: Django service failures through FastAPI HTTP endpoints."""

import httpx
import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


EVENT_KEY = "EVT-CH01-901"
TOKEN = "issue121-service-token-" + "A" * 48

VALID_EVENT = {
    "event_key": EVENT_KEY,
    "chapter": "CH01",
    "trigger_type": "EVIDENCE_COLLECTED",
    "required_evidence_ids": ["E19"],
    "title": "Synthetic event",
    "text": "Safe test content.",
}


@pytest.fixture
def environment(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "issue121_failures.db"
    )
    app = create_app(
        repository,
        session_secret="issue121-session-secret-" + "x" * 40,
    )
    client = TestClient(app)

    created = client.post("/api/games")
    assert created.status_code == 201
    session_id = created.json()["sessionId"]

    completed = client.post(
        f"/api/games/{session_id}/prologue/complete"
    )
    assert completed.status_code == 200

    state = repository.load_state(session_id)
    updated = GameState.model_validate({
        **state.model_dump(mode="python"),
        "current_chapter": "CH01",
        "unlocked_chapters": ["CH00", "CH01"],
        "evidence": {"E19": {"stage": "found"}},
        "queued_story_events": ["STORY_020"],
        "revision": state.revision + 1,
    })
    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    app.state.story_event_bindings = {
        EVENT_KEY: StoryEventBinding(
            source_story_id="STORY_020",
            event_key=EVENT_KEY,
            chapter="CH01",
        )
    }

    return client, app, repository, session_id


def attach_django_client(app, handler):
    django_client = DjangoContentClient(
        base_url="http://127.0.0.1:8001",
        token=TOKEN,
        timeout_seconds=3.0,
        transport=httpx.MockTransport(handler),
    )
    app.state.django_content_client = django_client
    return django_client


def assert_state_unchanged(repository, session_id, revision):
    state = repository.load_state(session_id)
    assert state.acknowledged_story_events == []
    assert state.revision == revision


def failure_handler(scenario):
    def handler(request):
        assert request.headers["X-Content-Service-Token"] == TOKEN
        assert request.url.path.endswith(
            f"/events/{EVENT_KEY}/"
        )

        if scenario == "timeout":
            raise httpx.ReadTimeout(
                "PRIVATE_DJANGO_TRACE",
                request=request,
            )

        if scenario == "connection":
            raise httpx.ConnectError(
                "PRIVATE_DJANGO_TRACE",
                request=request,
            )

        if scenario == "invalid_json":
            return httpx.Response(
                200,
                content=b"{invalid-json",
            )

        if scenario == "private_fields":
            return httpx.Response(
                200,
                json={
                    **VALID_EVENT,
                    "internal_secret": "PRIVATE_DJANGO_TRACE",
                },
            )

        if scenario == "oversized":
            return httpx.Response(
                200,
                content=b"x" * 65_537,
            )

        if scenario == "unauthorized":
            return httpx.Response(
                403,
                json={"detail": "PRIVATE_DJANGO_TRACE"},
            )

        if scenario == "server_error":
            return httpx.Response(
                500,
                json={"detail": "PRIVATE_DJANGO_TRACE"},
            )

        raise AssertionError(f"Unknown scenario: {scenario}")

    return handler


@pytest.mark.parametrize(
    "scenario",
    [
        "timeout",
        "connection",
        "invalid_json",
        "private_fields",
        "oversized",
        "unauthorized",
        "server_error",
    ],
)
def test_django_failure_returns_503_without_ack(
    environment,
    scenario,
):
    client, app, repository, session_id = environment

    django_client = attach_django_client(
        app,
        failure_handler(scenario),
    )

    base = f"/api/games/{session_id}/story-events"
    path = f"{base}/{EVENT_KEY}"
    revision = repository.load_state(session_id).revision

    try:
        for method, url in [
            ("GET", f"{base}/pending"),
            ("GET", path),
            ("POST", f"{path}/ack"),
        ]:
            response = client.request(method, url)

            assert response.status_code == 503
            assert response.json() == {
                "detail": "Content service unavailable"
            }
            assert "PRIVATE_DJANGO_TRACE" not in response.text

        assert_state_unchanged(
            repository,
            session_id,
            revision,
        )
    finally:
        django_client.close()


def test_unapproved_django_event_remains_hidden(environment):
    client, app, repository, session_id = environment

    django_client = attach_django_client(
        app,
        lambda request: httpx.Response(
            404,
            json={"detail": "PRIVATE_DJANGO_TRACE"},
        ),
    )

    base = f"/api/games/{session_id}/story-events"
    path = f"{base}/{EVENT_KEY}"
    revision = repository.load_state(session_id).revision

    try:
        pending = client.get(f"{base}/pending")
        detail = client.get(path)
        ack = client.post(f"{path}/ack")

        assert pending.status_code == 200
        assert pending.json() == {"items": []}
        assert detail.status_code == 404
        assert ack.status_code == 404

        for response in (pending, detail, ack):
            assert "PRIVATE_DJANGO_TRACE" not in response.text

        assert_state_unchanged(
            repository,
            session_id,
            revision,
        )
    finally:
        django_client.close()


def test_real_django_client_contract_and_ack(environment):
    client, app, repository, session_id = environment

    requests_seen = []

    def handler(request):
        requests_seen.append(request)
        assert request.url.path == (
            "/api/content/internal/cases/"
            f"CASE-001/events/{EVENT_KEY}/"
        )
        return httpx.Response(200, json=VALID_EVENT)

    django_client = attach_django_client(app, handler)

    base = f"/api/games/{session_id}/story-events"
    path = f"{base}/{EVENT_KEY}"

    try:
        pending = client.get(f"{base}/pending")
        assert pending.status_code == 200
        assert len(pending.json()["items"]) == 1

        ack = client.post(f"{path}/ack")
        assert ack.status_code == 200
        assert ack.json()["created"] is True

        state = repository.load_state(session_id)
        assert state.acknowledged_story_events == ["STORY_020"]

        assert len(requests_seen) == 2
    finally:
        django_client.close()


def test_partial_pending_list_is_not_exposed(environment):
    client, app, repository, session_id = environment

    state = repository.load_state(session_id)
    updated = GameState.model_validate({
        **state.model_dump(mode="python"),
        "queued_story_events": [
            "STORY_020",
            "STORY_021",
        ],
        "revision": state.revision + 1,
    })
    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    app.state.story_event_bindings[
        "EVT-CH01-902"
    ] = StoryEventBinding(
        source_story_id="STORY_021",
        event_key="EVT-CH01-902",
        chapter="CH01",
    )

    def handler(request):
        if request.url.path.endswith("/EVT-CH01-901/"):
            return httpx.Response(200, json=VALID_EVENT)

        return httpx.Response(
            500,
            json={"detail": "PRIVATE_SECOND_EVENT"},
        )

    django_client = attach_django_client(app, handler)

    try:
        response = client.get(
            f"/api/games/{session_id}/story-events/pending"
        )

        assert response.status_code == 503
        assert response.json() == {
            "detail": "Content service unavailable"
        }
        assert "Synthetic event" not in response.text
        assert "PRIVATE_SECOND_EVENT" not in response.text

        assert repository.load_state(
            session_id
        ).acknowledged_story_events == []
    finally:
        django_client.close()
