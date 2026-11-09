"""Issue #62 - 게임 시작, 저장, 이어하기 및 NPC 선택 API 테스트."""

from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.schemas.game_state import GamePhase
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def make_app(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")

    app = create_app(
        repository,
        session_secret="test-secret-" + "a" * 32,
    )

    return app, repository


# ============================================================
# 1. 게임 생성
# ============================================================


def test_create_game(tmp_path):
    app, repository = make_app(tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/games")

        assert response.status_code == 201

        data = response.json()

        assert data["phase"] == "PROLOGUE"
        assert data["activeCharacterId"] == "C01"
        assert data["unlockedCharacters"] == ["C01"]
        assert data["collection"] == {
            "score": 0,
            "total": 21,
        }
        assert data["canAccuse"] is False
        assert data["attemptsLeft"] == 3
        assert data["revision"] == 0

        saved = repository.load_state(data["sessionId"])

        assert saved.score == 0
        assert saved.revision == 0
        assert saved.phase == GamePhase.PROLOGUE


# ============================================================
# 2. 게임 이어하기
# ============================================================


def test_resume_game(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        created = client.post("/api/games").json()

        session_id = created["sessionId"]

        response = client.get(f"/api/games/{session_id}")

        assert response.status_code == 200
        assert response.json() == created


# ============================================================
# 3. 익명 접근 차단
# ============================================================


def test_anonymous_access_is_rejected(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as owner:
        session_id = owner.post("/api/games").json()["sessionId"]

    with TestClient(app) as stranger:
        response = stranger.get(f"/api/games/{session_id}")

        assert response.status_code == 404


# ============================================================
# 4. 다른 세션 접근 차단
# ============================================================


def test_other_session_access_is_rejected(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as first:
        first.post("/api/games")

        with TestClient(app) as second:
            session_id = second.post("/api/games").json()["sessionId"]

            response = first.get(f"/api/games/{session_id}")

            assert response.status_code == 404


# ============================================================
# 5. 클라이언트 상태 변조 차단
# ============================================================


def test_client_cannot_override_game_state(tmp_path):
    app, _ = make_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/games",
            json={
                "score": 21,
                "attempts_left": 99,
            },
        )

        assert response.status_code == 422


# ============================================================
# 6. 프롤로그 완료
# ============================================================


def test_complete_prologue(tmp_path):
    app, repository = make_app(tmp_path)

    with TestClient(app) as client:
        created = client.post("/api/games").json()
        session_id = created["sessionId"]

        response = client.post(f"/api/games/{session_id}/prologue/complete")

        assert response.status_code == 200

        data = response.json()

        assert data["phase"] == "INVESTIGATION"
        assert data["revision"] == 1
        assert data["activeCharacterId"] == "C01"

        assert data["events"] == [
            {
                "type": "PHASE_CHANGED",
                "phase": "INVESTIGATION",
            }
        ]

        saved = repository.load_state(session_id)

        assert saved.phase == GamePhase.INVESTIGATION
        assert saved.revision == 1

        assert repository.load_selection(session_id) == (
            "C01",
            1,
        )


# ============================================================
# 7. 프롤로그 중복 완료 방지
# ============================================================


def test_complete_prologue_is_idempotent(tmp_path):
    app, repository = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = client.post("/api/games").json()["sessionId"]

        url = f"/api/games/{session_id}/prologue/complete"

        first = client.post(url)
        second = client.post(url)

        assert first.status_code == 200
        assert second.status_code == 200

        first_data = first.json()
        second_data = second.json()

        # 중복 요청이 게임 상태를 변경하지 않아야 합니다.
        assert first_data["phase"] == "INVESTIGATION"
        assert second_data["phase"] == "INVESTIGATION"

        assert first_data["revision"] == 1
        assert second_data["revision"] == 1

        # 최초 전환에서만 이벤트가 발생합니다.
        assert len(first_data["events"]) == 1
        assert second_data["events"] == []

        saved = repository.load_state(session_id)

        assert saved.revision == 1


# ============================================================
# 8. 해금된 NPC 선택
# ============================================================


def test_select_unlocked_character(tmp_path):
    app, repository = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = client.post("/api/games").json()["sessionId"]

        prologue_response = client.post(f"/api/games/{session_id}/prologue/complete")

        assert prologue_response.status_code == 200

        response = client.post(f"/api/games/{session_id}/characters/C01/select")

        assert response.status_code == 200

        data = response.json()

        assert data["activeCharacterId"] == "C01"
        assert data["phase"] == "INVESTIGATION"
        assert data["revision"] == 1

        assert data["events"] == [
            {
                "type": "NPC_SELECTED",
                "characterId": "C01",
            }
        ]

        assert repository.load_selection(session_id) == (
            "C01",
            1,
        )


# ============================================================
# 9. 미해금 NPC 선택 차단
# ============================================================


def test_locked_character_rejected(tmp_path):
    app, repository = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = client.post("/api/games").json()["sessionId"]

        client.post(f"/api/games/{session_id}/prologue/complete")

        # C02는 초기 상태에서 해금되지 않았습니다.
        response = client.post(f"/api/games/{session_id}/characters/C02/select")

        assert response.status_code == 403

        restored_response = client.get(f"/api/games/{session_id}")

        assert restored_response.status_code == 200

        restored = restored_response.json()

        # 차단 이후에도 기존 NPC 선택이 유지되어야 합니다.
        assert restored["activeCharacterId"] == "C01"

        assert repository.load_selection(session_id) == (
            "C01",
            1,
        )


# ============================================================
# 10. 조사 단계 이전 NPC 선택 차단
# ============================================================


def test_select_character_requires_investigation(tmp_path):
    app, repository = make_app(tmp_path)

    with TestClient(app) as client:
        session_id = client.post("/api/games").json()["sessionId"]

        # 프롤로그를 완료하지 않은 상태
        response = client.post(f"/api/games/{session_id}/characters/C01/select")

        assert response.status_code == 409

        saved = repository.load_state(session_id)

        assert saved.phase == GamePhase.PROLOGUE
        assert saved.revision == 0
