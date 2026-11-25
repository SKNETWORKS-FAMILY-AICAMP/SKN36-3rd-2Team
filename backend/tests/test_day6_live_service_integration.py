"""Issue #158 - Live external service integration tests."""

import asyncio
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from crimescene.api.app import create_app
from crimescene.api.chat_bootstrap import load_chat_runtime
from crimescene.api.django_content_client import (
    ContentServiceError,
    DjangoContentClient,
)
from crimescene.mcp.context import BoundMCPContext
from crimescene.mcp.server import create_readonly_mcp_server
from crimescene.retriever.authorized_hybrid_search import (
    search_authorized_hybrid_context,
)
from crimescene.retriever.graph_evidence_search import (
    search_character_evidence,
)
from crimescene.retriever.graph_search import (
    CHARACTER_IDS,
    search_character_relations,
)
from crimescene.retriever.multisource_rrf import (
    fuse_multisource_candidates,
)
from crimescene.retriever.npc_graph_knowledge_guard import (
    restrict_npc_graph_knowledge,
)
from crimescene.retriever.query_graph_retriever import (
    QuestionGraphContext,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import GamePhase, GameState
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


@pytest.fixture
def slow_django():
    """Run a real HTTP server that delays its response."""

    received = Event()
    release = Event()

    class SlowHandler(BaseHTTPRequestHandler):

        def do_GET(self):
            received.set()
            release.wait(timeout=10)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        SlowHandler,
    )

    thread = Thread(
        target=server.serve_forever,
        daemon=True,
    )

    thread.start()

    try:
        yield (
            f"http://127.0.0.1:{server.server_port}",
            received,
        )

    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_live_django_read_timeout(slow_django):
    """Verify a real HTTP read timeout without mocking."""

    base_url, received = slow_django

    with DjangoContentClient(
        base_url=base_url,
        token="timeout-test-" + "x" * 40,
        timeout_seconds=0.3,
    ) as client, pytest.raises(ContentServiceError) as captured:
        client.get_evidence_requirements(
            "CASE-001",
            "E01",
        )

    assert received.is_set()

    assert isinstance(
        captured.value.__cause__,
        httpx.ReadTimeout,
    )


def test_live_agent_django_timeout(game, slow_django):
    """Reject a collaboration when approval lookup times out."""

    app, client, repository, _, state, query = game

    base_url, received = slow_django

    with DjangoContentClient(
        base_url=base_url,
        token="timeout-test-" + "x" * 40,
        timeout_seconds=0.3,
    ) as delayed:

        app.state.django_content_client = delayed

        response = client.post(
            agent_url(state, "assist"),
            json=request_body(state, query, "assist"),
        )

    assert received.is_set()

    assert response.status_code == 503

    assert "deduction" not in response.json()
    assert "hint" not in response.json()

    assert "127.0.0.1" not in response.text
    assert "timeout-test-" not in response.text
    assert "traceback" not in response.text.lower()

    assert repository.load_state(
        state.session_id
    ) == state


def test_live_graph_relation_policy(resources):
    """Verify real Neo4j relations against GameState policies."""

    initial = create_initial_state("day6-graph-policy")

    empty = GameState.model_validate({
        **initial.model_dump(mode="python"),
        "phase": GamePhase.INVESTIGATION,
        "unlocked_characters": sorted(CHARACTER_IDS),
        "outcome": "ONGOING",
    })

    driver = resources.neo4j_driver
    edges = resources.trusted_edges

    checked = set()
    restricted = set()

    for edge in edges:

        characters = {
            edge.source_id,
            edge.target_id,
        } & CHARACTER_IDS

        if not characters:
            continue

        character_id = min(characters)

        neighbor = (
            edge.target_id
            if edge.source_id == character_id
            else edge.source_id
        )

        before = search_character_relations(
            driver,
            character_id,
            empty,
            edges,
            top_k=100,
        )

        before_ids = {
            item.edge_id
            for item in before
        }

        if (
            edge.access_scope != "public"
            or neighbor in resources.evidence_rules
        ):
            assert edge.edge_id not in before_ids
            restricted.add(edge.edge_id)

        evidence_ids = set(edge.required_evidence)
        presented = {}

        for value in edge.required_presentations:
            npc_id, evidence_id = value.split(":")
            evidence_ids.add(evidence_id)
            presented.setdefault(npc_id, []).append(evidence_id)

        if neighbor in resources.evidence_rules:
            evidence_ids.add(neighbor)

        ending = edge.required_ending

        allowed = GameState.model_validate({
            **empty.model_dump(mode="python"),
            "phase": (
                GamePhase.FINISHED
                if ending is not None
                else GamePhase.INVESTIGATION
            ),
            "evidence": {
                eid: {"stage": "found"}
                for eid in evidence_ids
            },
            "presented": presented,
            "flags": list(edge.required_flags),
            "score": sum(
                resources.evidence_rules[eid].score
                for eid in evidence_ids
            ),
            "outcome": (
                "SUCCESS"
                if ending == "DEEP"
                else ending or "ONGOING"
            ),
            "deep_eligible": ending == "DEEP",
        })

        after = search_character_relations(
            driver,
            character_id,
            allowed,
            edges,
            top_k=100,
        )

        assert edge.edge_id in {
            item.edge_id
            for item in after
        }, edge.edge_id

        checked.add(edge.edge_id)

        if ending == "DEEP":
            normal = allowed.model_copy(
                update={"deep_eligible": False}
            )

            result = search_character_relations(
                driver,
                character_id,
                normal,
                edges,
                top_k=100,
            )

            assert edge.edge_id not in {
                item.edge_id
                for item in result
            }

        locked = allowed.model_copy(
            update={"unlocked_characters": []}
        )

        assert search_character_relations(
            driver,
            character_id,
            locked,
            edges,
        ) == []

    assert checked
    assert restricted

    print("Verified Relation Count:", len(checked))
    print("Restricted Relation Count:", len(restricted))


def test_live_graph_npc_knowledge_scope(resources):
    """Verify real evidence graph and NPC knowledge boundaries."""

    initial = create_initial_state("day6-npc-graph-policy")
    rules = resources.evidence_rules
    driver = resources.neo4j_driver

    empty = GameState.model_validate({
        **initial.model_dump(mode="python"),
        "phase": GamePhase.INVESTIGATION,
        "unlocked_characters": sorted(CHARACTER_IDS),
        "outcome": "ONGOING",
    })

    collected = GameState.model_validate({
        **empty.model_dump(mode="python"),
        "evidence": {
            evidence_id: {"stage": "found"}
            for evidence_id in rules
        },
        "score": sum(rule.score for rule in rules.values()),
    })

    verified = set()

    for character_id in sorted(CHARACTER_IDS):

        expected = {
            evidence_id
            for evidence_id, rule in rules.items()
            if rule.holder == character_id
        }

        assert search_character_evidence(
            driver,
            character_id,
            empty,
            rules,
        ) == []

        results = search_character_evidence(
            driver,
            character_id,
            collected,
            rules,
            top_k=100,
        )

        actual = {
            item.evidence_id
            for item in results
        }

        assert actual == expected

        if not results:
            continue

        graph = QuestionGraphContext(
            character_id=character_id,
            matched_entity_ids=(),
            relations=(),
            evidence=tuple(results),
        )

        candidates = fuse_multisource_candidates(
            [],
            [],
            graph,
        )

        denied = restrict_npc_graph_knowledge(
            candidates,
            graph,
            state=collected,
            active_character_id=character_id,
            trusted_edges=resources.trusted_edges,
            evidence_rules=rules,
        )

        assert denied.candidates == ()
        assert denied.graph_context.evidence == ()

        permitted_id = min(expected)

        permitted = restrict_npc_graph_knowledge(
            candidates,
            graph,
            state=collected,
            active_character_id=character_id,
            trusted_edges=resources.trusted_edges,
            evidence_rules=rules,
            known_evidence_ids=[permitted_id],
        )

        assert {
            item.evidence_id
            for item in permitted.graph_context.evidence
        } == {permitted_id}

        assert {
            item.item_id
            for item in permitted.candidates
        } == {permitted_id}

        verified.update(actual)

    assert verified == set(rules)

    print("Verified Evidence Holders:", len(verified))
