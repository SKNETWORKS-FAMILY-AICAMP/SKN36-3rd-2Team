
"""Issue #134 - FastAPI 세션 소유권 및 MCP 연결 검증."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from mcp import Client

from crimescene.api.app import COOKIE_NAME, create_app
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

SESSION_SECRET = "mcp-owner-test-" + "x" * 40


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "mcp-owner.sqlite3"
    )
    app = create_app(
        repository,
        session_secret=SESSION_SECRET,
    )

    # 실제 인스턴스를 사용하되, 조회하지 않는 외부 서비스는
    # 테스트에서 연결하지 않습니다.
    resources = NPCRAGResources(
        personas={},
        qdrant_client=None,
        neo4j_driver=None,
        embedder=None,
        encoder=None,
        trusted_records=(),
        documents=(),
        npc_cards=(),
        registry=(),
        trusted_edges=(),
        evidence_rules={
            "E01": EvidenceRule(
                name="검증용 증거",
                score=2,
                holder="C01",
                prerequisites=[],
                presentation=[],
                q=[],
            ),
        },
        evaluator=PolicyEvaluator({}),
    )

    django_client = DjangoContentClient(
        base_url="http://localhost:8001",
        token="x" * 40,
    )

    app.state.dialogue_resources = resources
    app.state.django_content_client = django_client

    # 테스트에서만 등록하는 진단용 경로입니다.
    # 실제 서비스 코드에는 이 HTTP 경로를 추가하지 않습니다.
    @app.get("/api/games/{session_id}/__test__/mcp")
    async def probe_mcp(
        session_id: str,
        request: Request,
    ):
        server = app.state.create_owner_scoped_mcp_server(
            session_id,
            request,
            request.cookies.get(COOKIE_NAME),
        )

        async with Client(server) as client:
            result = await client.call_tool(
                "get_game_context",
                {},
            )

        assert not result.is_error
        return result.structured_content

    yield app, repository

    django_client.close()


def create_game(client: TestClient) -> str:
    response = client.post("/api/games")

    assert response.status_code == 201
    return response.json()["sessionId"]


def mcp_path(session_id: str) -> str:
    return f"/api/games/{session_id}/__test__/mcp"


def test_authenticated_owner_can_execute_mcp(runtime):
    app, repository = runtime

    with TestClient(app) as client:
        session_id = create_game(client)

        before = repository.load_state(
            session_id
        ).model_dump(mode="json")

        response = client.get(mcp_path(session_id))

        assert response.status_code == 200

        payload = response.json()

        assert payload["phase"] == "PROLOGUE"
        assert payload["current_chapter"] == "CH00"
        assert payload["collected_evidence_ids"] == []

        # MCP 응답에 세션 식별자를 노출하지 않습니다.
        assert session_id not in str(payload)
        assert "session_id" not in payload

        after = repository.load_state(
            session_id
        ).model_dump(mode="json")

        assert after == before


def test_anonymous_mcp_access_rejected(runtime):
    app, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)

        client.cookies.clear()

        response = client.get(mcp_path(session_id))

        assert response.status_code == 404


def test_other_player_mcp_access_rejected(runtime):
    app, _ = runtime

    with TestClient(app) as player_a:
        session_a = create_game(player_a)

        with TestClient(app) as player_b:
            session_b = create_game(player_b)

            assert player_a.get(
                mcp_path(session_a)
            ).status_code == 200

            # A의 쿠키로 B의 MCP에 접근할 수 없습니다.
            assert player_a.get(
                mcp_path(session_b)
            ).status_code == 404

            assert player_b.get(
                mcp_path(session_a)
            ).status_code == 404


def test_missing_rag_runtime_fails_closed(runtime):
    app, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)

        app.state.dialogue_resources = None

        response = client.get(mcp_path(session_id))

        assert response.status_code == 503


def test_missing_django_client_fails_closed(runtime):
    app, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)

        app.state.django_content_client = None

        response = client.get(mcp_path(session_id))

        assert response.status_code == 503


def test_mcp_not_exposed_as_public_endpoint(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "isolated.sqlite3"
    )
    app = create_app(
        repository,
        session_secret=SESSION_SECRET,
    )

    paths = {
        route.path
        for route in app.routes
        if isinstance(getattr(route, "path", None), str)
    }

    assert "/mcp" not in paths
    assert "/api/mcp" not in paths
    assert "/api/games/{session_id}/__test__/mcp" not in paths
