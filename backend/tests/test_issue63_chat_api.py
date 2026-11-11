"""Issue #63 - NPC 대화 API 검증."""

"""Issue #63 - NPC 대화 API 검증."""

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import ChatRequest, create_app
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def make_app(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")

    app = create_app(
        repository,
        session_secret="test-secret-" + "a" * 32,
    )

    return app, repository


def start_game(client):
    response = client.post("/api/games")
    assert response.status_code == 201

    session_id = response.json()["sessionId"]

    response = client.post(f"/api/games/{session_id}/prologue/complete")

    assert response.status_code == 200

    return session_id


def test_chat_requires_engine(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = start_game(client)

        response = client.post(
            f"/api/games/{session_id}/chat",
            json={"question": "안녕하세요."},
        )

        assert response.status_code == 503


def test_chat_rejects_prologue(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = client.post("/api/games").json()["sessionId"]

        response = client.post(
            f"/api/games/{session_id}/chat",
            json={"question": "안녕하세요."},
        )

        assert response.status_code == 409


def test_chat_rejects_empty_question(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = start_game(client)

        response = client.post(
            f"/api/games/{session_id}/chat",
            json={"question": "   "},
        )

        assert response.status_code == 422


def test_chat_rejects_uncollected_evidence(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = start_game(client)

        response = client.post(
            f"/api/games/{session_id}/chat",
            json={
                "question": "이 증거를 보시겠습니까?",
                "presentedEvidenceId": "E01",
            },
        )

        assert response.status_code == 403


def test_other_player_cannot_chat(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as owner:
        session_id = start_game(owner)

    with TestClient(app) as stranger:
        response = stranger.post(
            f"/api/games/{session_id}/chat",
            json={"question": "안녕하세요."},
        )

        assert response.status_code == 404


def test_chat_accepts_200_characters():
    question = "가" * 200

    request = ChatRequest(question=question)

    assert request.question == question


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "가" * 201},
        {
            "question": "가" * 201,
            "presentedEvidenceId": "E01",
        },
        {"question": ""},
        {"question": " " * 200},
    ],
)
def test_chat_rejects_invalid_question_length(
    tmp_path,
    payload,
):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = start_game(client)

        response = client.post(
            f"/api/games/{session_id}/chat",
            json=payload,
        )

        assert response.status_code == 422
