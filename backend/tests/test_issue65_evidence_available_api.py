"""Issue #65 - no evidence metadata leaks before the acquisition policy passes."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def evidence_game(tmp_path):
    repo = SQLiteCase001Repository(tmp_path / "evidence-available.sqlite3")
    app = create_app(repo, session_secret="test-secret-" + "a" * 32)
    rules = {
        "E01": EvidenceRule(
            name="비공개 테스트 증거",
            score=1,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
    }
    app.state.dialogue_resources = SimpleNamespace(evidence_rules=rules)
    app.state.acquisition_policy_ids = {"E01": "POL-TEST-ACQUIRE-E01"}
    app.state.acquisition_evaluator = PolicyEvaluator(
        {
            "POL-TEST-ACQUIRE-E01": AccessPolicy(
                required_evidence=[],
                required_presentations=[],
                required_flags=[],
                required_ending=None,
                required_topics=[],
                required_disclosed_cards=["K-TEST-1"],
                required_character="C01",
            )
        }
    )
    with TestClient(app) as client:
        created = client.post("/api/games")
        assert created.status_code == 201, created.text
        session_id = created.json()["sessionId"]
        transitioned = client.post(f"/api/games/{session_id}/prologue/complete")
        assert transitioned.status_code == 200, transitioned.text
        yield client, app, repo, session_id


def _advance_state(repo, session_id, **updates):
    original = repo.load_state(session_id)
    changed = GameState.model_validate(
        {
            **original.model_dump(),
            **updates,
            "revision": original.revision + 1,
        }
    )
    repo.commit_state(expected_state=original, updated_state=changed)


def test_no_undisclosed_evidence_visible(evidence_game):
    client, _, _, sid = evidence_game
    response = client.get(f"/api/games/{sid}/evidence/available")
    assert response.status_code == 200, response.text
    assert response.json() == {"items": []}
    hidden = client.get(f"/api/games/{sid}/evidence/E01")
    assert hidden.status_code == 404
    assert "비공개 테스트 증거" not in hidden.text


def test_available_after_disclosure_only(evidence_game):
    client, _, repo, sid = evidence_game
    _advance_state(repo, sid, disclosed_cards=["K-TEST-1"])
    response = client.get(f"/api/games/{sid}/evidence/available")
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"evidenceId": "E01", "name": "비공개 테스트 증거", "score": 1}
    ]


def test_collected_evidence_has_safe_detail_only(evidence_game):
    client, _, repo, sid = evidence_game
    _advance_state(
        repo,
        sid,
        disclosed_cards=["K-TEST-1"],
        evidence={"E01": EvidenceState(stage="found").model_dump()},
        score=1,
    )
    assert client.get(f"/api/games/{sid}/evidence/available").json() == {"items": []}
    response = client.get(f"/api/games/{sid}/evidence/E01")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["title"] == "비공개 테스트 증거"
    assert detail["body"] is None
    assert detail["acquiredBy"] is None
    assert detail["holderId"] == "C01"


def test_other_client_cannot_see_evidence(evidence_game):
    _, app, repo, sid = evidence_game
    _advance_state(repo, sid, disclosed_cards=["K-TEST-1"])
    with TestClient(app) as stranger:
        assert stranger.get(f"/api/games/{sid}/evidence/available").status_code == 404
        assert stranger.get(f"/api/games/{sid}/evidence/E01").status_code == 404
