"""Issue #120 - Django 증거 해금 정책 연동 테스트."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.scenario.loaders.unlock_graph_loader import Case001UnlockRules
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

TOKEN = "issue120-test-token-" + "x" * 48


@pytest.fixture
def game_app(tmp_path):
    """격리된 SQLite 저장소와 증거 정책으로 테스트 앱을 생성합니다."""

    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")
    app = create_app(
        repository,
        session_secret="issue120-session-" + "s" * 40,
    )

    rules = {
        evidence_id: EvidenceRule(
            name=f"증거 {evidence_id}",
            score=2,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for evidence_id in ("E01", "E02")
    }

    policies = {
        f"POL-{evidence_id}": AccessPolicy(
            required_character="C01",
            required_disclosed_cards=[],
            required_evidence=[],
            required_presentations=[],
            required_flags=[],
            required_ending=None,
            required_topics=[],
        )
        for evidence_id in rules
    }

    evaluator = PolicyEvaluator(policies)

    app.state.dialogue_resources = SimpleNamespace(
        evidence_rules=rules,
        evaluator=evaluator,
    )
    app.state.dialogue_flag_config = Case001UnlockRules(
        npc_rules={},
        flag_requirements={},
        flag_sources={},
    )
    app.state.acquisition_policy_ids = {
        evidence_id: f"POL-{evidence_id}" for evidence_id in rules
    }
    app.state.acquisition_evaluator = evaluator
    app.state.django_evidence_gate_enabled = True

    return app, repository


def connect_django(app, handler):
    """MockTransport 기반 Django 클라이언트를 등록합니다."""

    django = DjangoContentClient(
        base_url="http://127.0.0.1:8001",
        token=TOKEN,
        transport=httpx.MockTransport(handler),
    )
    app.state.django_content_client = django
    return django


def approved_handler(request):
    """E02는 E01을 요구하고, E01에는 선행 조건이 없습니다."""

    assert request.headers["X-Content-Service-Token"] == TOKEN

    path = request.url.path
    assert path.startswith("/api/content/internal/cases/CASE-001/evidence/")

    if path.endswith("/E01/requirements/"):
        evidence_id = "E01"
        prerequisites = []
    elif path.endswith("/E02/requirements/"):
        evidence_id = "E02"
        prerequisites = ["E01"]
    else:
        raise AssertionError("예상하지 못한 증거 조회 요청")

    return httpx.Response(
        200,
        json={
            "evidence_id": evidence_id,
            "prerequisites": prerequisites,
            "player_unlock_verification_required": True,
        },
    )


def start_investigation(client):
    """게임을 생성하고 조사 단계로 전환합니다."""

    created = client.post("/api/games")
    assert created.status_code == 201

    session_id = created.json()["sessionId"]
    completed = client.post(f"/api/games/{session_id}/prologue/complete")
    assert completed.status_code == 200

    return session_id


def collect(client, session_id, evidence_id):
    return client.post(f"/api/games/{session_id}/evidence/{evidence_id}/collect")


def test_missing_prerequisite_is_blocked(game_app):
    """E01을 수집하지 않으면 E02를 획득할 수 없습니다."""

    app, repository = game_app

    with connect_django(app, approved_handler), TestClient(app) as client:
        session_id = start_investigation(client)
        response = collect(client, session_id, "E02")

    assert response.status_code == 403

    state = repository.load_state(session_id)
    assert state.evidence == {}
    assert state.score == 0


def test_collected_prerequisite_allows_evidence(game_app):
    """E01을 수집한 후 E02 수집이 허용됩니다."""

    app, repository = game_app

    with connect_django(app, approved_handler), TestClient(app) as client:
        session_id = start_investigation(client)

        first = collect(client, session_id, "E01")
        second = collect(client, session_id, "E02")

    assert first.status_code == 200
    assert second.status_code == 200

    state = repository.load_state(session_id)
    assert set(state.evidence) == {"E01", "E02"}
    assert state.score == 4


def test_disabled_gate_preserves_legacy_behavior(game_app):
    """기능 플래그가 꺼지면 기존 증거 수집 정책을 유지합니다."""

    app, repository = game_app
    app.state.django_evidence_gate_enabled = False

    # Django 클라이언트 없이도 기존 규칙으로 E02를 수집합니다.
    with TestClient(app) as client:
        session_id = start_investigation(client)
        response = collect(client, session_id, "E02")

    assert response.status_code == 200
    assert "E02" in repository.load_state(session_id).evidence


def test_missing_django_client_fails_closed(game_app):
    """Django 클라이언트가 없으면 수집을 중단합니다."""

    app, repository = game_app

    with TestClient(app) as client:
        session_id = start_investigation(client)
        response = collect(client, session_id, "E02")

    assert response.status_code == 503
    assert repository.load_state(session_id).evidence == {}


@pytest.mark.parametrize("status_code", [404, 500])
def test_django_http_errors_fail_closed(game_app, status_code):
    """미승인 증거 및 Django 서버 오류를 차단합니다."""

    app, repository = game_app

    def handler(request):
        return httpx.Response(
            status_code,
            json={"detail": "PRIVATE_ERROR"},
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = start_investigation(client)
        response = collect(client, session_id, "E02")

    assert response.status_code == 503
    assert "PRIVATE_ERROR" not in response.text
    assert repository.load_state(session_id).evidence == {}


def test_django_timeout_fails_closed(game_app):
    """타임아웃 시 증거가 지급되지 않습니다."""

    app, repository = game_app

    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with connect_django(app, handler), TestClient(app) as client:
        session_id = start_investigation(client)
        response = collect(client, session_id, "E02")

    assert response.status_code == 503
    assert repository.load_state(session_id).evidence == {}


def test_invalid_requirements_fail_closed(game_app):
    """잘못된 선행 증거 ID는 수용하지 않습니다."""

    app, repository = game_app

    def handler(request):
        return httpx.Response(
            200,
            json={
                "evidence_id": "E02",
                "prerequisites": ["E99"],
                "player_unlock_verification_required": True,
            },
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = start_investigation(client)
        response = collect(client, session_id, "E02")

    assert response.status_code == 503
    assert repository.load_state(session_id).evidence == {}


def test_non_owner_cannot_collect(game_app):
    """세션 소유권 검사 이전에 Django를 호출하지 않습니다."""

    app, repository = game_app
    requests = []

    def handler(request):
        requests.append(request)
        return approved_handler(request)

    with (
        connect_django(app, handler),
        TestClient(app) as owner,
        TestClient(app) as stranger,
    ):
        session_id = start_investigation(owner)
        response = collect(stranger, session_id, "E02")

    assert response.status_code == 404
    assert requests == []
    assert repository.load_state(session_id).evidence == {}


def test_mismatched_evidence_is_blocked(game_app):
    """요청한 증거와 다른 ID의 요구사항을 거부합니다."""

    app, repository = game_app

    def handler(request):
        return httpx.Response(
            200,
            json={
                "evidence_id": "E01",
                "prerequisites": [],
                "player_unlock_verification_required": True,
            },
        )

    with connect_django(app, handler), TestClient(app) as client:
        session_id = start_investigation(client)
        response = collect(client, session_id, "E02")

    assert response.status_code == 503
    assert repository.load_state(session_id).evidence == {}
