"""Issue #63: 수집 권한, 해금, 멱등성, SQLite 영구 저장 API 검증."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.loaders.unlock_graph_loader import Case001UnlockRules
from crimescene.scenario.npc_unlock import NPCUnlockRule
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

SECRET = "issue63-test-" + "x" * 40


def setup(tmp_path, *, ready=True):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")
    app = create_app(repository, session_secret=SECRET)

    if ready:
        evidence_rules = {
            "E01": EvidenceRule(
                name="C01의 증거",
                score=2,
                holder="C01",
                prerequisites=[],
                presentation=[],
                q=[],
            ),
            "E02": EvidenceRule(
                name="C05의 증거",
                score=3,
                holder="C05",
                prerequisites=[],
                presentation=[],
                q=[],
            ),
        }
        policies = {
            "POL-C01-E01": AccessPolicy(
                required_character="C01",
                required_disclosed_cards=["KC01-E01"],
                required_evidence=[],
                required_presentations=[],
                required_flags=[],
                required_ending=None,
                required_topics=[],
            ),
            "POL-C05-E02": AccessPolicy(
                required_character="C05",
                required_disclosed_cards=["KC05-E02"],
                required_evidence=[],
                required_presentations=[],
                required_flags=[],
                required_ending=None,
                required_topics=[],
            ),
        }
        app.state.dialogue_resources = SimpleNamespace(
            evidence_rules=evidence_rules,
            evaluator=PolicyEvaluator(policies),
        )
        app.state.dialogue_flag_config = Case001UnlockRules(
            npc_rules={"C02": NPCUnlockRule(required_evidence=frozenset({"E01"}))},
            flag_requirements={},
            flag_sources={},
        )
        app.state.acquisition_policy_ids = {"E01": "POL-C01-E01", "E02": "POL-C05-E02"}

    return app, repository


def create_investigation(client):
    created = client.post("/api/games")
    assert created.status_code == 201
    session_id = created.json()["sessionId"]
    done = client.post(f"/api/games/{session_id}/prologue/complete")
    assert done.status_code == 200
    return session_id


def disclose(repo, session_id):
    current = repo.load_state(session_id)
    updated = GameState.model_validate(
        {
            **current.model_dump(mode="python"),
            "disclosed_cards": [*current.disclosed_cards, "KC01-E01"],
            "revision": current.revision + 1,
        }
    )
    return repo.commit_state(expected_state=current, updated_state=updated)


def test_collection_requires_server_engine(tmp_path):
    app, repo = setup(tmp_path, ready=False)
    with TestClient(app) as client:
        sid = create_investigation(client)
        response = client.post(f"/api/games/{sid}/evidence/E01/collect")
        assert response.status_code == 503
        assert repo.load_state(sid).score == 0


def test_collection_requires_disclosed_card(tmp_path):
    app, repo = setup(tmp_path)
    with TestClient(app) as client:
        sid = create_investigation(client)
        response = client.post(f"/api/games/{sid}/evidence/E01/collect")
        assert response.status_code == 403
        assert repo.load_state(sid).evidence == {}


def test_collection_updates_score_and_unlocks(tmp_path):
    app, repo = setup(tmp_path)
    with TestClient(app) as client:
        sid = create_investigation(client)
        before = disclose(repo, sid)
        response = client.post(f"/api/games/{sid}/evidence/E01/collect")
        assert response.status_code == 200
        body = response.json()
        assert body["evidenceId"] == "E01"
        assert body["created"] is True
        assert body["collectedCount"] == 1
        assert body["totalCount"] == 2
        assert body["newlyUnlockedCharacters"] == ["C02"]
        assert body["game"]["collection"] == {"score": 2, "total": 21}
        assert body["game"]["revision"] == before.revision + 1
        assert body["game"]["events"] == [
            {"type": "EVIDENCE_COLLECTED", "evidenceId": "E01"},
            {"type": "NPC_UNLOCKED", "characterId": "C02"},
        ]
        assert repo.load_state(sid).evidence["E01"].stage == "found"
        assert repo.load_selection(sid) == ("C01", body["game"]["revision"])


def test_duplicate_collect_is_idempotent(tmp_path):
    app, repo = setup(tmp_path)
    with TestClient(app) as client:
        sid = create_investigation(client)
        disclose(repo, sid)
        path = f"/api/games/{sid}/evidence/E01/collect"
        first, second = client.post(path), client.post(path)
        assert first.status_code == second.status_code == 200
        assert second.json()["created"] is False
        assert second.json()["game"]["events"] == []
        assert first.json()["game"]["revision"] == second.json()["game"]["revision"]
        assert repo.load_state(sid).score == 2


def test_unowned_session_blocked(tmp_path):
    app, repo = setup(tmp_path)
    with TestClient(app) as owner:
        sid = create_investigation(owner)
        disclose(repo, sid)
    with TestClient(app) as stranger:
        response = stranger.post(f"/api/games/{sid}/evidence/E01/collect")
        assert response.status_code == 404
        assert repo.load_state(sid).score == 0


def test_wrong_holder_cannot_collect(tmp_path):
    app, repo = setup(tmp_path)
    with TestClient(app) as client:
        sid = create_investigation(client)
        response = client.post(f"/api/games/{sid}/evidence/E02/collect")
        assert response.status_code == 403
        assert repo.load_state(sid).evidence == {}


def test_invalid_evidence_id_rejected(tmp_path):
    app, _ = setup(tmp_path)
    with TestClient(app) as client:
        sid = create_investigation(client)
        response = client.post(f"/api/games/{sid}/evidence/E99/collect")
        assert response.status_code == 422


def test_collected_state_survives_restart(tmp_path):
    app, repo = setup(tmp_path)
    with TestClient(app) as client:
        sid = create_investigation(client)
        disclose(repo, sid)
        response = client.post(f"/api/games/{sid}/evidence/E01/collect")
        assert response.status_code == 200
    reopened = SQLiteCase001Repository(tmp_path / "game.sqlite3")
    saved = reopened.load_state(sid)
    assert saved.score == 2
    assert "C02" in saved.unlocked_characters
    assert saved.evidence["E01"].stage == "found"
