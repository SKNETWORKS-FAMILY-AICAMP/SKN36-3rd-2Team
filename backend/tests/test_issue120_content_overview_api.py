"""Issue #120 - 게임 세션 기반 Django 콘텐츠 조회 API 테스트."""

import httpx
import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

TOKEN = "test-content-token-" + "A" * 48

OVERVIEW = {
    "case": {
        "case_id": "CASE-001",
        "title": "테스트 사건",
        "status": "PUBLISHED",
    },
    "chapters": [
        {"code": "CH00", "order": 0, "title": "프롤로그"},
        {"code": "CH01", "order": 1, "title": "첫 번째 챕터"},
    ],
}


@pytest.fixture
def game_app(tmp_path):
    """독립된 SQLite DB를 사용하는 FastAPI 테스트 앱."""
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")
    app = create_app(
        repository,
        session_secret="issue120-test-" + "x" * 40,
    )
    return app, repository


def attach_django(app, handler):
    """모의 Django 서버를 FastAPI 앱에 연결합니다."""
    client = DjangoContentClient(
        base_url="http://127.0.0.1:8001",
        token=TOKEN,
        transport=httpx.MockTransport(handler),
    )
    app.state.django_content_client = client
    return client


def create_game(client):
    response = client.post("/api/games")
    assert response.status_code == 201
    return response.json()["sessionId"]


def content_url(session_id):
    return f"/api/games/{session_id}/content/overview"


def test_published_content_returns_200(game_app):
    """게시된 콘텐츠만 세션 소유자에게 공개합니다."""
    app, repository = game_app

    def handler(request):
        assert request.headers["X-Content-Service-Token"] == TOKEN
        assert request.url.path == ("/api/content/internal/cases/CASE-001/overview/")
        return httpx.Response(200, json=OVERVIEW)

    with attach_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(content_url(session_id))

    assert response.status_code == 200
    assert response.json() == {
        "caseId": "CASE-001",
        "title": "테스트 사건",
        "chapters": [
            {"code": "CH00", "order": 0, "title": "프롤로그"},
        ],
    }

    # 조회 요청이 게임 상태를 변경하지 않아야 합니다.
    assert repository.load_state(session_id).revision == 0


def test_draft_content_returns_404(game_app):
    """DRAFT 사건은 세션 소유자에게도 공개하지 않습니다."""
    app, _ = game_app

    def handler(request):
        payload = {
            **OVERVIEW,
            "case": {
                **OVERVIEW["case"],
                "status": "DRAFT",
            },
        }
        return httpx.Response(200, json=payload)

    with attach_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(content_url(session_id))

    assert response.status_code == 404
    assert "테스트 사건" not in response.text


def test_other_player_cannot_access_content(game_app):
    """타인의 세션 접근은 Django 호출 이전에 차단합니다."""
    app, _ = game_app
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=OVERVIEW)

    with attach_django(app, handler):
        with TestClient(app) as owner:
            session_id = create_game(owner)

        with TestClient(app) as stranger:
            response = stranger.get(content_url(session_id))

    assert response.status_code == 404
    assert requests == []


def test_missing_django_client_returns_503(game_app):
    """Django 클라이언트가 등록되지 않으면 503입니다."""
    app, _ = game_app

    with TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(content_url(session_id))

    assert response.status_code == 503


def test_django_failure_returns_503(game_app):
    """Django HTTP 장애를 FastAPI 503으로 변환합니다."""
    app, _ = game_app

    def handler(request):
        return httpx.Response(
            500,
            json={"detail": "SECRET_INTERNAL_ERROR"},
        )

    with attach_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(content_url(session_id))

    assert response.status_code == 503
    assert "SECRET_INTERNAL_ERROR" not in response.text
    assert TOKEN not in response.text


def test_case_id_mismatch_returns_503(game_app):
    """서버 저장 사건 ID와 Django 응답이 다르면 차단합니다."""
    app, _ = game_app

    def handler(request):
        payload = {
            **OVERVIEW,
            "case": {
                **OVERVIEW["case"],
                "case_id": "CASE-999",
            },
        }
        return httpx.Response(200, json=payload)

    with attach_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(content_url(session_id))

    assert response.status_code == 503
    assert "CASE-999" not in response.text


def test_invalid_django_response_returns_503(game_app):
    """잘못된 응답 스키마를 플레이어에게 전달하지 않습니다."""
    app, _ = game_app

    def handler(request):
        return httpx.Response(
            200,
            json={
                **OVERVIEW,
                "engine_secret": "PRIVATE_CASE_TRUTH",
            },
        )

    with attach_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(content_url(session_id))

    assert response.status_code == 503
    assert "PRIVATE_CASE_TRUTH" not in response.text


def test_unknown_game_session_returns_404(game_app):
    """존재하지 않는 게임은 콘텐츠 조회를 허용하지 않습니다."""
    app, _ = game_app

    with TestClient(app) as client:
        response = client.get(content_url("unknown-session"))

    assert response.status_code == 404


@pytest.mark.parametrize(
    "chapter",
    ["CH00", "CH01", "CH02", "CH03", "CH04"],
)
def test_overview_only_returns_unlocked_chapters(
    game_app,
    chapter,
):
    app, repository = game_app

    all_chapters = [
        {
            "code": f"CH0{i}",
            "order": i,
            "title": f"Chapter {i}",
        }
        for i in range(5)
    ]

    def handler(request):
        return httpx.Response(
            200,
            json={
                **OVERVIEW,
                "chapters": all_chapters,
            },
        )

    with attach_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)

        response = client.post(
            f"/api/games/{session_id}/prologue/complete"
        )
        assert response.status_code == 200

        current = repository.load_state(session_id)
        unlocked = [
            f"CH0{i}"
            for i in range(int(chapter[-1]) + 1)
        ]

        updated = GameState.model_validate(
            {
                **current.model_dump(mode="python"),
                "current_chapter": chapter,
                "unlocked_chapters": unlocked,
                "revision": current.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=current,
            updated_state=updated,
        )

        response = client.get(content_url(session_id))

    assert response.status_code == 200

    returned = response.json()["chapters"]

    assert [item["code"] for item in returned] == unlocked

    for item in all_chapters:
        if item["code"] not in unlocked:
            assert item["title"] not in response.text

    assert repository.load_state(session_id) == updated


def test_overview_rejects_concurrent_state_change(game_app):
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

        return httpx.Response(200, json=OVERVIEW)

    with attach_django(app, handler), TestClient(app) as client:
        session_id = create_game(client)
        response = client.get(content_url(session_id))

    assert response.status_code == 409
    assert "chapters" not in response.json()
