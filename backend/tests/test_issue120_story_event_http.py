from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.django_content_client import ApprovedStoryEvent
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

EVENT_KEY = "EVT-CH01-901"


class FakeApprovedContentClient:
    def get_approved_story_event(self, case_id, event_key):
        assert case_id == "CASE-001"
        assert event_key == EVENT_KEY

        return ApprovedStoryEvent.model_construct(
            event_key=EVENT_KEY,
            chapter="CH01",
            trigger_type="EVIDENCE_COLLECTED",
            required_evidence_ids=["E19"],
            title="TEST EVENT",
            text="Test content only.",
        )


def make_environment(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "story_event_http.db")
    app = create_app(
        repository,
        session_secret="test-session-secret-" + "x" * 40,
    )

    client = TestClient(app)
    created = client.post("/api/games")
    assert created.status_code == 201, created.text

    session_id = created.json()["sessionId"]

    prologue = client.post(f"/api/games/{session_id}/prologue/complete")
    assert prologue.status_code == 200, prologue.text

    state = repository.load_state(session_id)

    updated = GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            "current_chapter": "CH01",
            "unlocked_chapters": ["CH00", "CH01"],
            "evidence": {"E19": {"stage": "found"}},
            "queued_story_events": ["STORY_020"],
            "revision": state.revision + 1,
        }
    )

    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    app.state.story_event_bindings = {
        EVENT_KEY: StoryEventBinding(
            source_story_id="STORY_020",
            event_key=EVENT_KEY,
            chapter="CH01",
        ),
    }
    app.state.django_content_client = FakeApprovedContentClient()

    path = f"/api/games/{session_id}/story-events/{EVENT_KEY}"
    return client, app, repository, session_id, path


def test_get_pending_event(tmp_path):
    client, _, _, _, path = make_environment(tmp_path)

    response = client.get(path)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "eventKey": EVENT_KEY,
        "chapter": "CH01",
        "title": "TEST EVENT",
        "text": "Test content only.",
    }


def test_ack_and_retry(tmp_path):
    client, _, repository, session_id, path = make_environment(tmp_path)

    first = client.post(path + "/ack")
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True

    second = client.post(path + "/ack")
    assert second.status_code == 200, second.text
    assert second.json()["created"] is False

    assert second.json()["revision"] == first.json()["revision"]

    state = repository.load_state(session_id)
    assert state.acknowledged_story_events == ["STORY_020"]


def test_acknowledged_event_is_not_returned(tmp_path):
    client, _, _, _, path = make_environment(tmp_path)

    assert client.post(path + "/ack").status_code == 200
    assert client.get(path).status_code == 404


def test_unconfigured_binding_is_denied(tmp_path):
    client, app, _, _, path = make_environment(tmp_path)
    app.state.story_event_bindings = {}

    assert client.get(path).status_code == 404
    assert client.post(path + "/ack").status_code == 404


def test_missing_django_client_returns_503(tmp_path):
    client, app, _, _, path = make_environment(tmp_path)
    app.state.django_content_client = None

    assert client.get(path).status_code == 503
    assert client.post(path + "/ack").status_code == 503


def test_missing_evidence_is_denied(tmp_path):
    client, _, repository, session_id, path = make_environment(tmp_path)

    state = repository.load_state(session_id)
    updated = GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            "evidence": {},
            "revision": state.revision + 1,
        }
    )
    repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    assert client.get(path).status_code == 404
    assert client.post(path + "/ack").status_code == 404


def test_other_session_owner_is_denied(tmp_path):
    _, app, _, _session_id, path = make_environment(tmp_path)

    outsider = TestClient(app)

    assert outsider.get(path).status_code == 404
    assert outsider.post(path + "/ack").status_code == 404


def test_invalid_event_key_is_denied(tmp_path):
    client, _, _, session_id, _ = make_environment(tmp_path)

    path = f"/api/games/{session_id}/story-events/INVALID"

    assert client.get(path).status_code == 404
    assert client.post(path + "/ack").status_code == 404


def test_pending_list_returns_authorized_event(tmp_path):
    client, _, _, session_id, _ = make_environment(tmp_path)

    response = client.get(f"/api/games/{session_id}/story-events/pending")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "items": [
            {
                "eventKey": EVENT_KEY,
                "chapter": "CH01",
                "title": "TEST EVENT",
                "text": "Test content only.",
            }
        ]
    }


def test_pending_list_empty_after_ack(tmp_path):
    client, _, _, session_id, path = make_environment(tmp_path)
    pending_path = f"/api/games/{session_id}/story-events/pending"

    assert client.post(path + "/ack").status_code == 200

    response = client.get(pending_path)

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_pending_list_without_bindings_returns_empty(tmp_path):
    client, app, _, session_id, _ = make_environment(tmp_path)

    app.state.story_event_bindings = {}
    app.state.django_content_client = None

    response = client.get(f"/api/games/{session_id}/story-events/pending")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_pending_list_requires_session_owner(tmp_path):
    _, app, _, session_id, _ = make_environment(tmp_path)
    outsider = TestClient(app)

    response = outsider.get(f"/api/games/{session_id}/story-events/pending")

    assert response.status_code == 404


def test_pending_list_content_service_failure(tmp_path):
    client, app, _, session_id, _ = make_environment(tmp_path)

    app.state.django_content_client = None

    response = client.get(f"/api/games/{session_id}/story-events/pending")

    assert response.status_code == 503
