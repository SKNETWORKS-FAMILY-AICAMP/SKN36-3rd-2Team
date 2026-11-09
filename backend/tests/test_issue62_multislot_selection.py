"""Issue #62 - 다중 게임 쿠키와 NPC 선택 원자성 검증."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def make_app(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")
    app = create_app(repository, session_secret="test-secret-" + "a" * 32)
    return app, repository


def unlock_characters(repository, session_id, characters):
    """테스트 전용으로 서버 측 해금 결과를 저장합니다."""
    original = repository.load_state(session_id)
    updated = GameState.model_validate(
        {
            **original.model_dump(mode="python"),
            "unlocked_characters": characters,
            "revision": original.revision + 1,
        }
    )
    return repository.commit_state(expected_state=original, updated_state=updated)


def create_investigation_game(client):
    response = client.post("/api/games")
    assert response.status_code == 201
    session_id = response.json()["sessionId"]
    completed = client.post(f"/api/games/{session_id}/prologue/complete")
    assert completed.status_code == 200
    return session_id


def test_multiple_games_survive_new_game(tmp_path):
    app, _ = make_app(tmp_path)
    with TestClient(app) as client:
        first = client.post("/api/games").json()["sessionId"]
        second = client.post("/api/games").json()["sessionId"]
        assert first != second
        assert client.post(f"/api/games/{first}/prologue/complete").status_code == 200
        assert client.get(f"/api/games/{first}").json()["phase"] == "INVESTIGATION"
        assert client.get(f"/api/games/{second}").json()["phase"] == "PROLOGUE"


def test_reselect_same_character_is_idempotent(tmp_path):
    app, repo = make_app(tmp_path)
    with TestClient(app) as client:
        session_id = create_investigation_game(client)
        endpoint = f"/api/games/{session_id}/characters/C01/select"
        first = client.post(endpoint)
        second = client.post(endpoint)
        assert first.status_code == second.status_code == 200
        assert first.json()["revision"] == second.json()["revision"] == 1
        assert repo.load_selection(session_id) == ("C01", 1)


def test_select_unlocked_character_updates_both_revisions(tmp_path):
    app, repo = make_app(tmp_path)
    with TestClient(app) as client:
        session_id = create_investigation_game(client)
        unlocked = unlock_characters(repo, session_id, ["C01", "C02"])
        response = client.post(f"/api/games/{session_id}/characters/C02/select")
        assert response.status_code == 200
        assert response.json()["activeCharacterId"] == "C02"
        assert response.json()["revision"] == unlocked.revision + 1
        assert repo.load_selection(session_id) == ("C02", unlocked.revision + 1)
        assert repo.load_state(session_id).revision == unlocked.revision + 1


def test_stale_selection_cannot_overwrite(tmp_path):
    app, repo = make_app(tmp_path)
    with TestClient(app) as client:
        session_id = create_investigation_game(client)
        initial = unlock_characters(repo, session_id, ["C01", "C02", "C03"])
    updated = repo.select_character_atomic(expected_state=initial, character_id="C02")
    with pytest.raises(ValueError):
        repo.select_character_atomic(expected_state=initial, character_id="C03")
    assert repo.load_state(session_id) == updated
    assert repo.load_selection(session_id) == ("C02", updated.revision)


def test_failed_npc_selection_rolls_back_both_tables(tmp_path):
    app, repo = make_app(tmp_path)
    with TestClient(app) as client:
        session_id = create_investigation_game(client)
        initial = unlock_characters(repo, session_id, ["C01", "C02"])
    previous_selection = repo.load_selection(session_id)
    with sqlite3.connect(tmp_path / "game.sqlite3") as db:
        db.execute(
            """
            CREATE TRIGGER fail_selection BEFORE UPDATE ON npc_sessions
            BEGIN SELECT RAISE(ABORT, 'forced failure'); END
            """
        )
    with pytest.raises(sqlite3.DatabaseError):
        repo.select_character_atomic(expected_state=initial, character_id="C02")
    assert repo.load_state(session_id) == initial
    assert repo.load_selection(session_id) == previous_selection


def test_scoped_cookie_not_shared_with_stranger(tmp_path):
    app, _ = make_app(tmp_path)
    with TestClient(app) as owner:
        sid = owner.post("/api/games").json()["sessionId"]
        with TestClient(app) as stranger:
            assert stranger.get(f"/api/games/{sid}").status_code == 404
            assert (
                stranger.post(f"/api/games/{sid}/prologue/complete").status_code == 404
            )
