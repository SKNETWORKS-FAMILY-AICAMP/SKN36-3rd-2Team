"""Issue #165 - objective and inference API tests."""

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.investigation_progress import (
    InferenceRule,
    ObjectiveRule,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "inference.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="issue165-inference-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"

    app.state.approved_inference_rules = (
        InferenceRule(
            rule_id="LINK-001",
            inference_id="INF_ACCESS_WINDOW",
            chapter="CH03",
            evidence_ids=frozenset({"E21", "E23"}),
        ),
    )

    app.state.approved_objective_rules = (
        ObjectiveRule(
            objective_id="OBJ_FIND_CARD_USER",
            chapter="CH03",
            required_evidence=frozenset({"E21"}),
            target_evidence=frozenset({"E23"}),
        ),
        ObjectiveRule(
            objective_id="OBJ_RECONSTRUCT_ROUTE",
            chapter="CH03",
            required_evidence=frozenset({"E23"}),
            target_evidence=frozenset({"E24", "E25"}),
        ),
    )

    with TestClient(app) as client:
        response = client.post("/api/games")

        assert response.status_code == 201

        sid = response.json()["sessionId"]

        response = client.post(
            f"/api/games/{sid}/prologue/complete"
        )

        assert response.status_code == 200

        state = repository.load_state(sid)

        updated = GameState.model_validate({
            **state.model_dump(),
            "current_chapter": "CH03",
            "unlocked_chapters": [
                "CH00", "CH01", "CH03",
            ],
            "evidence": {
                "E21": {"stage": "found"},
                "E23": {"stage": "found"},
                "E25": {"stage": "found"},
            },
            "score": 7,
            "revision": state.revision + 1,
        })

        repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )

        yield app, client, repository, sid


def infer(
    runtime,
    evidence=None,
    revision=None,
    **extra,
):
    _, client, repository, sid = runtime

    state = repository.load_state(sid)

    return client.post(
        f"/api/games/{sid}/inferences",
        json={
            "evidenceIds": (
                ["E21", "E23"]
                if evidence is None
                else evidence
            ),
            "expectedRevision": (
                state.revision
                if revision is None
                else revision
            ),
            **extra,
        },
    )


def test_objective_status(runtime):
    _, client, _, sid = runtime

    response = client.get(
        f"/api/games/{sid}/objectives"
    )

    assert response.status_code == 200

    assert response.json()["items"] == [
        {
            "objectiveId": "OBJ_FIND_CARD_USER",
            "status": "COMPLETED",
        },
        {
            "objectiveId": "OBJ_RECONSTRUCT_ROUTE",
            "status": "ACTIVE",
        },
    ]


def test_valid_inference_persists(runtime):
    _, _, repository, sid = runtime

    before = repository.load_state(sid)

    response = infer(runtime)

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["created"] is True

    after = repository.load_state(sid)

    assert "INF_ACCESS_WINDOW" in after.flags
    assert after.revision == before.revision + 1
    assert after.score == before.score


def test_duplicate_inference_is_idempotent(runtime):
    assert infer(runtime).status_code == 200

    _, _, repository, sid = runtime
    before = repository.load_state(sid)

    response = infer(runtime)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert repository.load_state(sid) == before


def test_wrong_evidence_pair(runtime):
    _, _, repository, sid = runtime

    before = repository.load_state(sid)

    response = infer(runtime, ["E21", "E25"])

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert repository.load_state(sid) == before


def test_uncollected_evidence_denied(runtime):
    response = infer(runtime, ["E21", "E24"])

    assert response.status_code == 403


def test_duplicate_evidence_denied(runtime):
    response = infer(runtime, ["E21", "E21"])

    assert response.status_code == 422


def test_client_cannot_grant_inference(runtime):
    response = infer(
        runtime,
        flags=["INF_DEEP_GATE"],
    )

    assert response.status_code == 422


def test_stale_revision_denied(runtime):
    _, _, repository, sid = runtime

    state = repository.load_state(sid)

    response = infer(
        runtime,
        revision=state.revision - 1,
    )

    assert response.status_code == 409


def test_unapproved_rules_do_not_execute(runtime):
    app, _, repository, sid = runtime

    app.state.approved_inference_rules = ()

    before = repository.load_state(sid)

    response = infer(runtime)

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert repository.load_state(sid) == before


def test_protected_inference_cannot_be_registered():
    with pytest.raises(ValueError):
        InferenceRule(
            rule_id="LINK-030",
            inference_id="INF_DEEP_GATE",
            chapter="CH04",
            evidence_ids=frozenset({"E14", "E30"}),
        )


def test_other_player_cannot_submit(runtime):
    app, _, repository, sid = runtime

    before = repository.load_state(sid)

    with TestClient(app) as stranger:
        response = stranger.post(
            f"/api/games/{sid}/inferences",
            json={
                "evidenceIds": ["E21", "E23"],
                "expectedRevision": before.revision,
            },
        )

    assert response.status_code == 404
    assert repository.load_state(sid) == before
