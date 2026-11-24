"""Issue #120 - 게임 세션 기반 Scene 공개 API 통합 테스트."""

import httpx
import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

TOKEN = "issue120-scene-token-" + "x" * 48

SCENE = {
    "scene_id": "SC-0001",
    "chapter": "CH00",
    "title": "프롤로그",
    "scene_text": "사건이 시작됩니다.",
}


@pytest.fixture
def game_app(tmp_path):
    """격리된 SQLite 게임 DB를 사용하는 테스트 앱."""

    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")

    app = create_app(
        repository,
        session_secret="issue120-scene-secret-" + "s" * 40,
    )

    return app, repository


def connect_django(app, handler):
    """MockTransport 기반 Django 클라이언트를 연결합니다."""

    django = DjangoContentClient(
        base_url="http://127.0.0.1:8001",
        token=TOKEN,
        transport=httpx.MockTransport(handler),
    )

    app.state.django_content_client = django
    return django


def create_game(client):
    response = client.post("/api/games")
    assert response.status_code == 201
    return response.json()["sessionId"]


def scene_url(session_id, scene_id="SC-0001"):
    return f"/api/games/{session_id}/content/scenes/{scene_id}"


def test_approved_ch00_scene_returns_200(game_app):
    """세션 소유자에게 승인된 CH00 장면을 공개합니다."""

    app, repository = game_app

    def handler(request):
        assert request.headers["X-Content-Service-Token"] == TOKEN
        assert request.url.path == (
            "/api/content/internal/cases/CASE-001/scenes/SC-0001/"
        )
        return httpx.Response(200, json=SCENE)

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == 200
    assert response.json() == {
        "sceneId": "SC-0001",
        "chapter": "CH00",
        "title": "프롤로그",
        "sceneText": "사건이 시작됩니다.",
    }

    # 스토리 조회만으로 게임 상태가 변경되면 안 됩니다.
    assert repository.load_state(session_id).revision == 0


def test_locked_ch01_scene_returns_404(game_app):
    """미해금 챕터의 장면은 Django가 승인해도 공개하지 않습니다."""

    app, _ = game_app

    def handler(request):
        return httpx.Response(
            200,
            json={
                **SCENE,
                "chapter": "CH01",
                "scene_text": "미래 챕터의 비밀",
            },
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == 404
    assert "미래 챕터의 비밀" not in response.text


def test_non_owner_cannot_access_scene(game_app):
    """타인 세션은 Django 요청 이전에 차단합니다."""

    app, _ = game_app
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=SCENE)

    with connect_django(app, handler):
        with TestClient(app) as owner:
            session_id = create_game(owner)

        with TestClient(app) as stranger:
            response = stranger.get(scene_url(session_id))

    assert response.status_code == 404
    assert requests == []


def test_missing_django_client_returns_503(game_app):
    """콘텐츠 클라이언트가 없으면 안전하게 실패합니다."""

    app, _ = game_app

    with TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == 503


@pytest.mark.parametrize(
    ("django_status", "expected_status"),
    [
        (404, 404),
        (500, 503),
    ],
)
def test_django_http_error(
    game_app,
    django_status,
    expected_status,
):
    """미승인 장면과 서버 장애를 구분합니다."""

    app, _ = game_app

    def handler(request):
        return httpx.Response(
            django_status,
            json={"detail": "PRIVATE_SCENE_INFORMATION"},
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == expected_status
    assert "PRIVATE_SCENE_INFORMATION" not in response.text


def test_invalid_scene_id_returns_404(game_app):
    """잘못된 Scene ID는 Django 요청 이전에 차단합니다."""

    app, _ = game_app
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=SCENE)

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id, "INVALID"))

    assert response.status_code == 404
    assert requests == []


def test_scene_id_mismatch_returns_503(game_app):
    """요청과 다른 장면이 전달되면 차단합니다."""

    app, _ = game_app

    def handler(request):
        return httpx.Response(
            200,
            json={
                **SCENE,
                "scene_id": "SC-0002",
            },
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == 503


def test_invalid_scene_schema_returns_503(game_app):
    """필수 필드가 누락된 응답은 거부합니다."""

    app, _ = game_app

    def handler(request):
        return httpx.Response(
            200,
            json={
                "scene_id": "SC-0001",
                "chapter": "CH00",
            },
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == 503


def test_private_fields_are_rejected(game_app):
    """Django 내부 정보가 플레이어에게 유출되지 않아야 합니다."""

    app, _ = game_app

    def handler(request):
        return httpx.Response(
            200,
            json={
                **SCENE,
                "case_truth": "SECRET_PERPETRATOR",
            },
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == 503
    assert "SECRET_PERPETRATOR" not in response.text


def test_django_timeout_returns_503(game_app):
    """Django 응답 지연 시 스토리를 공개하지 않습니다."""

    app, _ = game_app

    def handler(request):
        raise httpx.ReadTimeout(
            "Django timeout",
            request=request,
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == 503


@pytest.mark.parametrize(
    "chapter",
    ["CH01", "CH02", "CH03", "CH04"],
)
def test_current_unlocked_scene_returns_200(game_app, chapter):
    """현재 해금된 챕터의 승인 장면을 반환합니다."""
    app, repository = game_app

    def handler(request):
        return httpx.Response(
            200,
            json={**SCENE, "chapter": chapter},
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)

        response = client.post(
            f"/api/games/{session_id}/prologue/complete"
        )
        assert response.status_code == 200

        current = repository.load_state(session_id)
        updated = GameState.model_validate(
            {
                **current.model_dump(mode="python"),
                "current_chapter": chapter,
                "unlocked_chapters": [
                    f"CH0{i}"
                    for i in range(int(chapter[-1]) + 1)
                ],
                "revision": current.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=current,
            updated_state=updated,
        )

        response = client.get(scene_url(session_id))

    assert response.status_code == 200
    assert response.json()["chapter"] == chapter
    assert repository.load_state(session_id) == updated


def test_previous_chapter_scene_is_blocked(game_app):
    """해금됐더라도 현재 챕터가 아닌 장면은 차단합니다."""
    app, repository = game_app

    def handler(request):
        return httpx.Response(200, json=SCENE)

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)

        response = client.post(
            f"/api/games/{session_id}/prologue/complete"
        )
        assert response.status_code == 200

        current = repository.load_state(session_id)
        updated = GameState.model_validate(
            {
                **current.model_dump(mode="python"),
                "current_chapter": "CH01",
                "unlocked_chapters": ["CH00", "CH01"],
                "revision": current.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=current,
            updated_state=updated,
        )

        response = client.get(scene_url(session_id))

    assert response.status_code == 404
    assert "sceneText" not in response.json()


def test_scene_read_rejects_concurrent_state_change(game_app):
    """Django 조회 도중 상태 변경 시 장면 반환을 차단합니다."""
    app, repository = game_app

    def handler(request):
        current = repository.load_state(session_id)
        updated = GameState.model_validate(
            {
                **current.model_dump(mode="python"),
                "revision": current.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=current,
            updated_state=updated,
        )

        return httpx.Response(200, json=SCENE)

    with connect_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(scene_url(session_id))

    assert response.status_code == 409
    assert "sceneText" not in response.json()
