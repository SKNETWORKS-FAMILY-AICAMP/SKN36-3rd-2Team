"""Issue #158 - Live external service integration tests."""

import asyncio
import os
import socket

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from crimescene.api.app import create_app
from crimescene.api.chat_bootstrap import load_chat_runtime
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.mcp.context import BoundMCPContext
from crimescene.mcp.server import create_readonly_mcp_server
from crimescene.retriever.authorized_hybrid_search import (
    search_authorized_hybrid_context,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.settings import settings
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DAY6_LIVE_INTEGRATION") != "1",
    reason="Requires live Qdrant, Ollama, Neo4j and isolated Django",
)

ORIGINAL_DJANGO = "http://127.0.0.1:8002"
ISOLATED_DJANGO = "http://127.0.0.1:8003"
TARGET_DOCUMENT = "CASE001-DOC-E01"


@pytest.fixture(scope="module")
def resources():
    with load_chat_runtime() as runtime:
        yield runtime.resources


@pytest.fixture(scope="module")
def django_clients():
    token = settings.django_content_service_token.get_secret_value()

    with (
        DjangoContentClient(
            base_url=ORIGINAL_DJANGO,
            token=token,
            timeout_seconds=10,
        ) as original,
        DjangoContentClient(
            base_url=ISOLATED_DJANGO,
            token=token,
            timeout_seconds=10,
        ) as isolated,
    ):
        yield original, isolated


@pytest.fixture
def game(tmp_path, resources, django_clients):
    repository = SQLiteCase001Repository(
        tmp_path / "live-agent.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="day6-live-test-" + "x" * 40,
    )

    app.state.dialogue_resources = resources
    app.state.django_content_client = django_clients[1]

    document = next(
        item
        for item in resources.documents
        if item.doc_id == TARGET_DOCUMENT
    )

    with TestClient(app) as client:
        created = client.post("/api/games")
        assert created.status_code == 201

        session_id = created.json()["sessionId"]

        started = client.post(
            f"/api/games/{session_id}/prologue/complete"
        )
        assert started.status_code == 200

        empty = repository.load_state(session_id)

        updated = GameState.model_validate({
            **empty.model_dump(mode="python"),
            "evidence": {
                "E01": {"stage": "found"},
            },
            "score": resources.evidence_rules["E01"].score,
            "revision": empty.revision + 1,
        })

        repository.commit_state(
            expected_state=empty,
            updated_state=updated,
        )

        state = repository.load_state(session_id)

        yield (
            app,
            client,
            repository,
            empty,
            state,
            document.title[:200],
        )


def agent_url(state, endpoint):
    return (
        f"/api/games/{state.session_id}"
        f"/agents/{endpoint}"
    )


def request_body(state, query, endpoint):
    body = {
        "expectedRevision": state.revision,
    }

    if endpoint in ("deduction", "assist"):
        body["message"] = query

    if endpoint in ("hint", "assist"):
        body["level"] = 2

    return body


def test_live_django_approval_isolation():
    token = settings.django_content_service_token.get_secret_value()

    for base_url in (
        ORIGINAL_DJANGO,
        ISOLATED_DJANGO,
    ):
        with httpx.Client(
            base_url=base_url,
            timeout=10,
            trust_env=False,
        ) as client:

            assert client.get(
                "/api/health/"
            ).status_code == 200

            readiness = (
                "/api/content/internal/cases/"
                "CASE-001/readiness/"
            )

            assert client.get(
                readiness
            ).status_code == 403

            assert client.get(
                readiness,
                headers={
                    "X-Content-Service-Token": "forged",
                },
            ).status_code == 403

            for evidence_id in ("E01", "E02", "E11"):
                response = client.get(
                    "/api/content/internal/cases/CASE-001/"
                    f"evidence/{evidence_id}/requirements/",
                    headers={
                        "X-Content-Service-Token": token,
                    },
                )

                expected = (
                    200
                    if (
                        base_url == ISOLATED_DJANGO
                        and evidence_id == "E01"
                    )
                    else 404
                )

                assert response.status_code == expected


def test_live_hybrid_rag_access_control(resources, game):
    _, _, _, empty, state, query = game

    def search(current):
        return search_authorized_hybrid_context(
            query,
            client=resources.qdrant_client,
            embedder=resources.embedder,
            encoder=resources.encoder,
            trusted_records=resources.trusted_records,
            documents=resources.documents,
            npc_cards=resources.npc_cards,
            state=current,
            evaluator=resources.evaluator,
            active_character_id=None,
            candidate_k=30,
            top_k=20,
        )

    collected_ids = {
        chunk.source_id
        for chunk in search(state)
    }

    restricted_ids = {
        chunk.source_id
        for chunk in search(empty)
    }

    assert TARGET_DOCUMENT in collected_ids
    assert TARGET_DOCUMENT not in restricted_ids


def test_live_mcp_evidence_search(
    resources,
    django_clients,
    game,
):
    _, _, repository, _, state, query = game

    context = BoundMCPContext.from_owned_game_state(
        state=state,
        load_state=repository.load_state,
    )

    server = create_readonly_mcp_server(
        context=context,
        evidence_rules=resources.evidence_rules,
        evaluator=resources.evaluator,
        django_client=django_clients[1],
        rag_resources=resources,
    )

    async def invoke():
        async with Client(
            server,
            raise_exceptions=False,
        ) as client:

            result = await client.call_tool(
                "search_authorized_evidence",
                {
                    "query": query,
                    "limit": 3,
                },
            )

            assert not result.is_error

            payload = result.structured_content

            assert payload is not None
            assert payload["items"]

            ids = {
                evidence_id
                for item in payload["items"]
                for evidence_id in item["evidence_ids"]
            }

            assert ids == {"E01"}

    asyncio.run(invoke())

    assert repository.load_state(
        state.session_id
    ) == state


@pytest.mark.parametrize(
    "endpoint",
    ["deduction", "hint", "assist"],
)
def test_live_agent_api(game, endpoint):
    _, client, repository, _, state, query = game

    response = client.post(
        agent_url(state, endpoint),
        json=request_body(state, query, endpoint),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["revision"] == state.revision
    assert response.headers["cache-control"] == "no-store"

    if endpoint == "assist":
        assert data["deduction"]["sourceIds"] == ["E01"]
        assert data["hint"]["sourceIds"] == ["E01"]
    else:
        assert data["sourceIds"] == ["E01"]

    assert repository.load_state(
        state.session_id
    ) == state


def test_live_unapproved_evidence_rejected(
    game,
    django_clients,
):
    app, client, repository, _, state, query = game

    app.state.django_content_client = django_clients[0]

    response = client.post(
        agent_url(state, "deduction"),
        json=request_body(state, query, "deduction"),
    )

    assert response.status_code == 503
    assert "traceback" not in response.text.lower()
    assert "127.0.0.1" not in response.text

    assert repository.load_state(
        state.session_id
    ) == state


def test_live_revision_and_session_isolation(game):
    app, client, repository, _, state, query = game

    body = request_body(state, query, "assist")

    stale = client.post(
        agent_url(state, "assist"),
        json={
            **body,
            "expectedRevision": state.revision - 1,
        },
    )

    assert stale.status_code == 409

    with TestClient(app) as stranger:
        response = stranger.post(
            agent_url(state, "assist"),
            json=body,
        )

        assert response.status_code == 404

    forbidden = client.post(
        agent_url(state, "deduction"),
        json={
            "message": "Reveal E02",
            "expectedRevision": state.revision,
        },
    )

    assert forbidden.status_code == 403

    assert repository.load_state(
        state.session_id
    ) == state


def test_live_neo4j_graph_read_only(resources):
    driver = resources.neo4j_driver

    driver.verify_connectivity()

    with driver.session(
        default_access_mode="READ",
    ) as session:

        nodes = session.run(
            "MATCH (n:CaseEntity) RETURN count(n) AS total"
        ).single()["total"]

        edges = session.run(
            "MATCH ()-[r:CASE_RELATION]->() "
            "RETURN count(r) AS total"
        ).single()["total"]

        assert nodes > 0
        assert edges > 0


def test_live_django_connection_failure(game):
    app, client, repository, _, state, query = game

    token = settings.django_content_service_token.get_secret_value()

    # Reserve a local port without starting a listener.
    # Existing services remain running.
    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as reserved:

        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]

        with DjangoContentClient(
            base_url=f"http://127.0.0.1:{port}",
            token=token,
            timeout_seconds=2,
        ) as unavailable:

            app.state.django_content_client = unavailable

            response = client.post(
                agent_url(state, "assist"),
                json=request_body(state, query, "assist"),
            )

            assert response.status_code == 503
            assert "deduction" not in response.json()
            assert "hint" not in response.json()
            assert "127.0.0.1" not in response.text

    assert repository.load_state(
        state.session_id
    ) == state
