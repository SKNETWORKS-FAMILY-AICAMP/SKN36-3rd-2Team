"""Issue #165 - investigation HTTP and atomic collection."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.scenario.content_compiler import (
    PROPOSED_SCORES,
    proposed_routes,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "investigation.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="issue165-investigation-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"

    settings = {
        "scene_approved": True,
        "evidence_approved": True,
        "django_prerequisites": [],
    }

    def handler(request):
        path = request.url.path

        if "/scenes/" in path or path == '/api/content/internal/cases/CASE-001/releases/v0.11.0/investigation-scenes/SC-0306/':
            if not settings["scene_approved"]:
                return httpx.Response(404)

            return httpx.Response(
                200,
                json={
                    "scene_id": ("SC-0306" if path == '/api/content/internal/cases/CASE-001/releases/v0.11.0/investigation-scenes/SC-0306/' else path.strip("/").split("/")[-1]),
                    "chapter": "CH03",
                    "title": "Test scene",
                    "scene_text": "Test investigation",
                },
            )

        if "/evidence/" in path:
            if not settings["evidence_approved"]:
                return httpx.Response(404)

            return httpx.Response(
                200,
                json={
                    "evidence_id": path.strip("/").split("/")[-2],
                    "prerequisites": settings["django_prerequisites"],
                    "player_unlock_verification_required": True,
                },
            )

        return httpx.Response(404)

    django = DjangoContentClient(
        base_url="http://127.0.0.1:8002",
        token="x" * 40,
        transport=httpx.MockTransport(handler),
    )

    with TestClient(app) as client:
        response = client.post("/api/games")
        assert response.status_code == 201

        session_id = response.json()["sessionId"]

        response = client.post(
            f"/api/games/{session_id}/prologue/complete"
        )

        assert response.status_code == 200

        legacy_scores = dict(zip(
            [f"E{i:02d}" for i in range(1, 11)],
            [1, 2, 3, 2, 3, 3, 2, 2, 1, 2],
            strict=True,
        ))

        rules = {
            eid: EvidenceRule(
                name=f"Test {eid}",
                score=score,
                holder="C03",
                prerequisites=[],
                presentation=[],
                q=[],
            )
            for eid, score in {
                **legacy_scores,
                **PROPOSED_SCORES,
            }.items()
        }

        app.state.dialogue_resources = SimpleNamespace(
            evidence_rules=rules,
        )

        app.state.approved_acquisition_routes = {
            eid: proposed_routes(eid, "CH03")
            for eid in ("E23", "E25")
        }

        app.state.approved_investigation_actions = frozenset({
            "inspect-sensor-record",
            "inspect-emergency-door-record",
        })

        app.state.django_content_client = django

        state = repository.load_state(session_id)

        updated = GameState.model_validate({
            **state.model_dump(),
            "current_chapter": "CH03",
            "unlocked_chapters": [
                "CH00", "CH01", "CH03",
            ],
            "evidence": {
                "E21": {"stage": "found"},
            },
            "score": rules["E21"].score,
            "revision": state.revision + 1,
        })

        repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )

        try:
            yield app, client, repository, session_id, settings
        finally:
            django.close()


def perform(
    runtime,
    action="inspect-sensor-record",
    revision=None,
    **extra,
):
    _, client, repository, session_id, _ = runtime

    state = repository.load_state(session_id)

    return client.post(
        f"/api/games/{session_id}/investigations/{action}",
        json={
            "expectedRevision": (
                state.revision if revision is None else revision
            ),
            **extra,
        },
    )


def test_sensor_action_collects_e23(runtime):
    _, _, repository, session_id, _ = runtime

    before = repository.load_state(session_id)

    response = perform(runtime)

    assert response.status_code == 200

    after = repository.load_state(session_id)

    assert "E23" in after.evidence
    assert after.score == before.score + 3
    assert after.revision == before.revision + 1
    assert "ACT_SENSOR_RECORD_INSPECTED" in after.flags
    assert response.json()["total"] == 65


def test_door_requires_e23(runtime):
    response = perform(
        runtime,
        "inspect-emergency-door-record",
    )

    assert response.status_code == 403


def test_sensor_then_door(runtime):
    assert perform(runtime).status_code == 200

    response = perform(
        runtime,
        "inspect-emergency-door-record",
    )

    assert response.status_code == 200

    _, _, repository, session_id, _ = runtime

    state = repository.load_state(session_id)

    assert {"E21", "E23", "E25"}.issubset(state.evidence)
    assert state.score == 7


def test_duplicate_action_no_extra_score(runtime):
    assert perform(runtime).status_code == 200

    _, _, repository, session_id, _ = runtime

    before = repository.load_state(session_id)

    response = perform(runtime)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert repository.load_state(session_id) == before


def test_unapproved_action_denied(runtime):
    app, _, repository, session_id, _ = runtime

    app.state.approved_investigation_actions = frozenset()

    before = repository.load_state(session_id)

    assert perform(runtime).status_code == 404
    assert repository.load_state(session_id) == before


def test_stale_revision_denied(runtime):
    _, _, repository, session_id, _ = runtime

    before = repository.load_state(session_id)

    response = perform(
        runtime,
        revision=before.revision - 1,
    )

    assert response.status_code == 409
    assert repository.load_state(session_id) == before


def test_client_cannot_inject_flags(runtime):
    response = perform(
        runtime,
        flags=["consent_and_safety_verified"],
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "approval",
    ["scene_approved", "evidence_approved"],
)
def test_django_denial_rolls_back(runtime, approval):
    _, _, repository, session_id, settings = runtime

    settings[approval] = False

    before = repository.load_state(session_id)

    response = perform(runtime)

    assert response.status_code in (404, 503)
    assert repository.load_state(session_id) == before


def test_django_prerequisite_enforced(runtime):
    _, _, repository, session_id, settings = runtime

    settings["django_prerequisites"] = ["E22"]

    before = repository.load_state(session_id)

    assert perform(runtime).status_code == 403
    assert repository.load_state(session_id) == before


def test_other_player_cannot_investigate(runtime):
    app, _, repository, session_id, _ = runtime

    before = repository.load_state(session_id)

    with TestClient(app) as stranger:
        response = stranger.post(
            f"/api/games/{session_id}/investigations/"
            "inspect-sensor-record",
            json={
                "expectedRevision": before.revision,
            },
        )

    assert response.status_code == 404
    assert repository.load_state(session_id) == before

def configure_e26_test_runtime(
    runtime,
    *,
    approved=True,
    has_e20=True,
):
    app, _, repository, session_id, settings = runtime

    app.state.e26_section_a_approved = approved
    app.state.investigation_release_version = "v0.11.0"

    app.state.approved_investigation_actions |= frozenset({
        "inspect-e26-a",
    })

    app.state.approved_acquisition_routes["E26"] = (
        proposed_routes("E26", "CH03")
    )

    settings["django_prerequisites"] = ["E20"]

    if has_e20:
        state = repository.load_state(session_id)
        rules = app.state.dialogue_resources.evidence_rules

        updated = GameState.model_validate({
            **state.model_dump(),
            "evidence": {
                **state.model_dump()["evidence"],
                "E20": {"stage": "found"},
            },
            "score": state.score + rules["E20"].score,
            "revision": state.revision + 1,
        })

        repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )


def test_e26_http_collects_once(runtime):
    configure_e26_test_runtime(runtime)

    _, _, repository, session_id, _ = runtime
    before = repository.load_state(session_id)

    response = perform(runtime, "inspect-e26-a")

    assert response.status_code == 200, response.text
    assert response.json()["created"] is True
    assert response.json()["evidenceId"] == "E26"

    after = repository.load_state(session_id)

    assert after.score == before.score + 3
    assert after.revision == before.revision + 1
    assert "E26" in after.evidence
    assert "E26-A" not in after.evidence
    assert "ACT_AUDIT_LOG_ACCESS_VERIFIED" in after.flags

    duplicate = perform(runtime, "inspect-e26-a")

    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert repository.load_state(session_id) == after


def test_e26_http_requires_section_approval(runtime):
    configure_e26_test_runtime(runtime, approved=False)

    _, _, repository, session_id, _ = runtime
    before = repository.load_state(session_id)

    response = perform(runtime, "inspect-e26-a")

    assert response.status_code == 403
    assert repository.load_state(session_id) == before


def test_e26_http_requires_e20(runtime):
    configure_e26_test_runtime(runtime, has_e20=False)

    _, _, repository, session_id, _ = runtime
    before = repository.load_state(session_id)

    response = perform(runtime, "inspect-e26-a")

    assert response.status_code == 403
    assert repository.load_state(session_id) == before


@pytest.mark.parametrize(
    "action",
    ["inspect-e26-b", "inspect-e26-c"],
)
def test_e26_http_restricted_sections_unavailable(runtime, action):
    configure_e26_test_runtime(runtime)

    assert perform(runtime, action).status_code == 404


@pytest.mark.parametrize(
    "approval",
    ["scene_approved", "evidence_approved"],
)
def test_e26_http_django_denial_rolls_back(runtime, approval):
    configure_e26_test_runtime(runtime)

    _, _, repository, session_id, settings = runtime
    settings[approval] = False

    before = repository.load_state(session_id)
    response = perform(runtime, "inspect-e26-a")

    assert response.status_code in (404, 503)
    assert repository.load_state(session_id) == before


def test_e26_http_rejects_client_section_approval(runtime):
    configure_e26_test_runtime(runtime, approved=False)

    response = perform(
        runtime,
        "inspect-e26-a",
        section_a_approved=True,
    )

    assert response.status_code == 422
