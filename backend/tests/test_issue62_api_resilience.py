"""Issue #62 - API 재시작, 소유권 및 동시 요청 검증."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from crimescene.api.app import COOKIE_NAME, create_app
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

SECRET = "test-secret-" + "a" * 32


def make_app(db_path, *, secret=SECRET):
    repository = SQLiteCase001Repository(db_path)

    app = create_app(
        repository,
        session_secret=secret,
    )

    return app, repository


def test_game_survives_server_restart(tmp_path):
    """서버 재시작 후 저장된 진행 상태를 복원합니다."""

    db_path = tmp_path / "game.sqlite3"

    app, _ = make_app(db_path)

    with TestClient(app) as client:
        created = client.post("/api/games")

        assert created.status_code == 201

        session_id = created.json()["sessionId"]

        completed = client.post(f"/api/games/{session_id}/prologue/complete")

        assert completed.status_code == 200

        owner_cookie = client.cookies.get(COOKIE_NAME)

    assert owner_cookie is not None

    # 새로운 저장소 및 FastAPI 인스턴스로 재시작을 재현합니다.
    restarted_app, restarted_repository = make_app(db_path)

    with TestClient(restarted_app) as client:
        response = client.get(
            f"/api/games/{session_id}",
            headers={
                "Cookie": f"{COOKIE_NAME}={owner_cookie}",
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert data["phase"] == "INVESTIGATION"
    assert data["revision"] == 1
    assert data["activeCharacterId"] == "C01"

    saved = restarted_repository.load_state(session_id)

    assert saved.revision == 1


def test_changed_secret_rejects_old_cookie(tmp_path):
    """세션 비밀키가 달라지면 기존 쿠키를 거부합니다."""

    db_path = tmp_path / "game.sqlite3"

    app, _ = make_app(db_path)

    with TestClient(app) as client:
        session_id = client.post("/api/games").json()["sessionId"]

        owner_cookie = client.cookies.get(COOKIE_NAME)

    assert owner_cookie is not None

    changed_app, _ = make_app(
        db_path,
        secret="different-secret-" + "b" * 32,
    )

    with TestClient(changed_app) as client:
        response = client.get(
            f"/api/games/{session_id}",
            headers={
                "Cookie": f"{COOKIE_NAME}={owner_cookie}",
            },
        )

    assert response.status_code == 404


def test_non_owner_cannot_modify_game(tmp_path):
    """소유권이 없는 플레이어는 게임을 변경할 수 없습니다."""

    app, repository = make_app(tmp_path / "game.sqlite3")

    with TestClient(app) as owner:
        session_id = owner.post("/api/games").json()["sessionId"]

    with TestClient(app) as stranger:
        prologue = stranger.post(f"/api/games/{session_id}/prologue/complete")

        selection = stranger.post(f"/api/games/{session_id}/characters/C01/select")

    assert prologue.status_code == 404
    assert selection.status_code == 404

    state = repository.load_state(session_id)

    assert state.phase == "PROLOGUE"
    assert state.revision == 0


def test_concurrent_prologue_requests(tmp_path):
    """동시 요청에도 프롤로그가 한 번만 완료됩니다."""

    app, repository = make_app(tmp_path / "game.sqlite3")

    with TestClient(app) as owner:
        session_id = owner.post("/api/games").json()["sessionId"]

        owner_cookie = owner.cookies.get(COOKIE_NAME)

    assert owner_cookie is not None

    url = f"/api/games/{session_id}/prologue/complete"
    barrier = Barrier(2)

    def send_request():
        with TestClient(app) as client:
            barrier.wait(timeout=10)

            return client.post(
                url,
                headers={
                    "Cookie": f"{COOKIE_NAME}={owner_cookie}",
                },
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(send_request)
        second = executor.submit(send_request)

        responses = [
            first.result(),
            second.result(),
        ]

    # 첫 요청은 성공하고 경쟁 요청은 성공 또는 충돌 처리됩니다.
    assert all(response.status_code in (200, 409) for response in responses)

    assert any(response.status_code == 200 for response in responses)

    # 상태 전환 이벤트는 최대 한 번만 발생해야 합니다.
    phase_events = [
        event
        for response in responses
        if response.status_code == 200
        for event in response.json()["events"]
        if event["type"] == "PHASE_CHANGED"
    ]

    assert len(phase_events) == 1

    saved = repository.load_state(session_id)

    assert saved.phase == "INVESTIGATION"
    assert saved.revision == 1

    assert repository.load_selection(session_id) == (
        "C01",
        1,
    )
