"""Issue #63 - NPC 대화 기록 조회 API 테스트."""

from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def make_app(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")

    app = create_app(
        repository,
        session_secret="test-secret-" + "a" * 32,
    )

    return app, repository


def start_investigation(client):
    response = client.post("/api/games")
    assert response.status_code == 201

    session_id = response.json()["sessionId"]

    response = client.post(f"/api/games/{session_id}/prologue/complete")
    assert response.status_code == 200

    return session_id


def test_empty_chat_history(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = start_investigation(client)

        response = client.get(f"/api/games/{session_id}/chats/C01")

        assert response.status_code == 200
        assert response.json()["messages"] == []


def test_saved_chat_history(tmp_path):
    app, repository = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = start_investigation(client)

        state = repository.load_state(session_id)
        store = NPCSessionStore(repository=repository)

        quote = "그날 밤 복도에서 발소리가 들렸습니다."

        store.append_verified_exchange(
            state,
            "C01",
            user_message="안녕하세요?",
            reply=NPCGroundedReply(
                text=(
                    "제가 확인한 자료에는 이렇게 나와 있어요.\n"
                    f"“{quote}” (근거: TEST-SOURCE-01)"
                ),
                source_ids=("TEST-SOURCE-01",),
                grounded=True,
            ),
        )

        response = client.get(f"/api/games/{session_id}/chats/C01")

        assert response.status_code == 200

        data = response.json()

        assert data["messages"] == [
            {
                "userMessage": "안녕하세요?",
                "displayText": quote,
            }
        ]

        # 내부 출처 정보는 사용자에게 노출하지 않습니다.
        assert "TEST-SOURCE-01" not in response.text


def test_locked_npc_history_rejected(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = start_investigation(client)

        response = client.get(f"/api/games/{session_id}/chats/C02")

        assert response.status_code == 403


def test_other_player_history_rejected(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as owner:
        session_id = start_investigation(owner)

    with TestClient(app) as stranger:
        response = stranger.get(f"/api/games/{session_id}/chats/C01")

        assert response.status_code == 404


def test_history_does_not_change_revision(tmp_path):
    app, repository = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = start_investigation(client)

        before = repository.load_state(session_id)

        response = client.get(f"/api/games/{session_id}/chats/C01")

        assert response.status_code == 200

        after = repository.load_state(session_id)

        assert after == before
