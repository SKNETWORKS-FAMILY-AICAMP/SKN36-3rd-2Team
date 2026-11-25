"""Issue #157 - Authenticated Multi-Agent HTTP integration tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import COOKIE_NAME, create_app
from crimescene.api.django_content_client import (
    DjangoContentClient,
    EvidenceRequirements,
)
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.mcp.client import (
    MCPToolClient,
    MCPToolExecutionError,
    MCPToolTimeoutError,
    MCPToolValidationError,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

ENDPOINTS = ("deduction", "hint", "assist")


def make_document(evidence_id):
    return PlayerDocument(
        doc_id=f"DOC-{evidence_id}",
        case_id="CASE-001",
        title=f"Document {evidence_id}",
        body=f"TEST_DOCUMENT_BODY_{evidence_id}",
        family="evidence",
        access_scope="collected_evidence",
        truth_status="documented_in_game",
        source_evidence_ids=[evidence_id],
        known_by_character_ids=["C01"],
        source_doc_ids=[],
        required_evidence=[evidence_id],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        protected_fact_ids=[],
        incident_year=None,
        incident_years=[],
        source_refs=[],
        record_id=f"REC-{evidence_id}",
        point_id=f"POINT-{evidence_id}",
        policy_id=f"POLICY-{evidence_id}",
        state_version="1",
        content_version="1",
        build_id="test",
        content_hash="test",
        search_text=f"Document {evidence_id}",
    )


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    repository = SQLiteCase001Repository(
        tmp_path / "agent-http.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="agent-http-test-" + "x" * 40,
    )

    rules = {
        evidence_id: EvidenceRule(
            name=name,
            score=score,
            holder=holder,
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for evidence_id, name, score, holder in (
            ("E01", "Public schedule", 2, "C01"),
            ("E02", "HIDDEN_EVIDENCE_NAME", 3, "C02"),
        )
    }

    documents = (
        make_document("E01"),
        make_document("E02"),
    )

    resources = NPCRAGResources(
        personas={},
        qdrant_client=None,
        neo4j_driver=None,
        embedder=None,
        encoder=None,
        trusted_records=(),
        documents=documents,
        npc_cards=(),
        registry=(),
        trusted_edges=(),
        evidence_rules=rules,
        evaluator=PolicyEvaluator({}),
    )

    django = DjangoContentClient(
        base_url="http://localhost:8001",
        token="x" * 40,
    )

    def approved_requirements(case_id, evidence_id):
        assert case_id == "CASE-001"

        return EvidenceRequirements(
            evidence_id=evidence_id,
            prerequisites=[],
            player_unlock_verification_required=True,
        )

    approval = Mock(
        side_effect=approved_requirements
    )

    monkeypatch.setattr(
        django,
        "get_evidence_requirements",
        approval,
    )

    # Mock external retrieval only.
    # MCP evidence filtering remains active.
    search = Mock(
        return_value=[
            SimpleNamespace(
                source_type="player_document",
                source_id=document.doc_id,
                content=document.body,
            )
            for document in documents
        ]
    )

    monkeypatch.setattr(
        "crimescene.mcp.server.search_authorized_hybrid_context",
        search,
    )

    app.state.dialogue_resources = resources
    app.state.django_content_client = django

    yield app, repository, search, approval

    django.close()


def create_game(client, *, investigation=True):
    response = client.post("/api/games")

    assert response.status_code == 201

    session_id = response.json()["sessionId"]

    if investigation:
        response = client.post(
            f"/api/games/{session_id}/prologue/complete"
        )

        assert response.status_code == 200

    return session_id


def collect_evidence(repository, session_id, evidence_id="E01"):
    before = repository.load_state(session_id)

    updated = GameState.model_validate(
        {
            **before.model_dump(mode="python"),
            "evidence": {
                evidence_id: {"stage": "found"}
            },
            "score": 2 if evidence_id == "E01" else 3,
            "revision": before.revision + 1,
        }
    )

    return repository.commit_state(
        expected_state=before,
        updated_state=updated,
    )


def url(session_id, endpoint):
    return f"/api/games/{session_id}/agents/{endpoint}"


def body(endpoint, revision, **updates):
    payload = {
        "expectedRevision": revision,
    }

    if endpoint in ("deduction", "assist"):
        payload["message"] = "Review relevant records"

    if endpoint in ("hint", "assist"):
        payload["level"] = 2

    payload.update(updates)

    return payload


# Successful HTTP -> Agent -> MCP execution.


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_authenticated_execution(runtime, endpoint):
    app, repository, search, approval = runtime

    with TestClient(app) as client:
        session_id = create_game(client)

        before = collect_evidence(
            repository,
            session_id,
        )

        response = client.post(
            url(session_id, endpoint),
            json=body(endpoint, before.revision),
        )

        assert response.status_code == 200, response.text

        data = response.json()

        assert data["revision"] == before.revision
        assert response.headers["cache-control"] == "no-store"

        if endpoint == "assist":
            assert data["deduction"]["sourceIds"] == ["E01"]
            assert data["hint"]["sourceIds"] == ["E01"]
            assert data["hint"]["level"] == 2
        else:
            assert data["sourceIds"] == ["E01"]
            assert data["agentType"] == endpoint

        assert "E02" not in response.text
        assert "HIDDEN_EVIDENCE_NAME" not in response.text
        assert "TEST_DOCUMENT_BODY" not in response.text
        assert session_id not in response.text

        if endpoint == "hint":
            search.assert_not_called()
            approval.assert_not_called()
        else:
            search.assert_called_once()
            approval.assert_called_once_with(
                "CASE-001",
                "E01",
            )

        assert repository.load_state(session_id) == before


@pytest.mark.parametrize("level", [1, 2, 3])
def test_hint_levels(runtime, level):
    app, repository, search, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = collect_evidence(repository, session_id)

        response = client.post(
            url(session_id, "hint"),
            json=body(
                "hint",
                state.revision,
                level=level,
            ),
        )

        assert response.status_code == 200, response.text

        data = response.json()

        assert data["level"] == level
        assert data["collectedCount"] == 1

        if level == 1:
            assert data["sourceIds"] == []
            assert data["suggestedCharacterId"] is None
        else:
            assert data["sourceIds"] == ["E01"]

        if level == 3:
            assert (
                data["suggestedCharacterId"]
                in state.unlocked_characters
            )

        search.assert_not_called()


def test_empty_evidence_collaboration(runtime):
    app, repository, search, approval = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = repository.load_state(session_id)

        response = client.post(
            url(session_id, "assist"),
            json=body("assist", state.revision),
        )

        assert response.status_code == 200

        data = response.json()

        assert data["deduction"]["sourceIds"] == []
        assert (
            data["deduction"]["status"]
            == "INSUFFICIENT_EVIDENCE"
        )

        assert data["hint"]["sourceIds"] == []
        assert data["hint"]["status"] == "NO_EVIDENCE"

        search.assert_not_called()
        approval.assert_not_called()

        assert repository.load_state(session_id) == state


# Session ownership and authentication.


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_anonymous_access_rejected(runtime, endpoint):
    app, repository, search, approval = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = repository.load_state(session_id)

        client.cookies.clear()

        response = client.post(
            url(session_id, endpoint),
            json=body(endpoint, state.revision),
        )

        assert response.status_code == 404

        search.assert_not_called()
        approval.assert_not_called()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_cross_session_access_rejected(runtime, endpoint):
    app, repository, search, approval = runtime

    with TestClient(app) as owner:
        session_id = create_game(owner)
        state = collect_evidence(repository, session_id)

        with TestClient(app) as stranger:
            other_id = create_game(stranger)

            assert other_id != session_id

            response = stranger.post(
                url(session_id, endpoint),
                json=body(endpoint, state.revision),
            )

            assert response.status_code == 404

        search.assert_not_called()
        approval.assert_not_called()

        assert repository.load_state(session_id) == state


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_forged_cookie_rejected(runtime, endpoint):
    app, repository, search, _ = runtime

    with TestClient(app) as owner:
        session_id = create_game(owner)
        state = repository.load_state(session_id)

        with TestClient(app) as stranger:
            response = stranger.post(
                url(session_id, endpoint),
                headers={
                    "Cookie": (
                        f"{COOKIE_NAME}_{session_id}=forged;"
                        f" {COOKIE_NAME}=forged"
                    )
                },
                json=body(endpoint, state.revision),
            )

            assert response.status_code == 404

        search.assert_not_called()


# Strict HTTP request validation.


@pytest.mark.parametrize(
    ("endpoint", "updates"),
    [
        ("deduction", {"message": ""}),
        ("deduction", {"message": "   "}),
        ("deduction", {"message": "a" * 201}),
        ("deduction", {"message": 123}),
        ("hint", {"level": 0}),
        ("hint", {"level": 4}),
        ("hint", {"level": True}),
        ("hint", {"level": "2"}),
        ("assist", {"level": 4}),
        ("assist", {"message": ""}),
        ("assist", {"expectedRevision": -1}),
        ("assist", {"expectedRevision": True}),
        ("assist", {"expectedRevision": "1"}),
    ],
)
def test_invalid_request_rejected(runtime, endpoint, updates):
    app, repository, search, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = repository.load_state(session_id)

        response = client.post(
            url(session_id, endpoint),
            json=body(
                endpoint,
                state.revision,
                **updates,
            ),
        )

        assert response.status_code == 422
        search.assert_not_called()


@pytest.mark.parametrize(
    "field",
    [
        "sessionId",
        "caseId",
        "agentType",
        "characterId",
        "collectedEvidenceIds",
        "unlockedCharacters",
        "sourceIds",
        "deductionResult",
        "includeHidden",
        "token",
    ],
)
def test_untrusted_fields_rejected(runtime, field):
    app, repository, search, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = repository.load_state(session_id)

        response = client.post(
            url(session_id, "assist"),
            json=body(
                "assist",
                state.revision,
                **{field: "forged"},
            ),
        )

        assert response.status_code == 422
        search.assert_not_called()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_missing_revision_rejected(runtime, endpoint):
    app, _, search, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)

        payload = body(endpoint, 0)
        del payload["expectedRevision"]

        response = client.post(
            url(session_id, endpoint),
            json=payload,
        )

        assert response.status_code == 422
        search.assert_not_called()


# Revision and game phase checks.


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_stale_revision_rejected(runtime, endpoint):
    app, repository, search, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = collect_evidence(repository, session_id)

        response = client.post(
            url(session_id, endpoint),
            json=body(endpoint, state.revision - 1),
        )

        assert response.status_code == 409
        search.assert_not_called()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_prologue_execution_rejected(runtime, endpoint):
    app, repository, search, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(
            client,
            investigation=False,
        )

        state = repository.load_state(session_id)

        response = client.post(
            url(session_id, endpoint),
            json=body(endpoint, state.revision),
        )

        assert response.status_code == 409
        search.assert_not_called()


# Evidence access and content approval.


@pytest.mark.parametrize(
    "endpoint",
    ["deduction", "assist"],
)
def test_uncollected_evidence_rejected(runtime, endpoint):
    app, repository, search, approval = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = collect_evidence(repository, session_id)

        response = client.post(
            url(session_id, endpoint),
            json=body(
                endpoint,
                state.revision,
                message="Reveal E02",
            ),
        )

        assert response.status_code == 403

        search.assert_not_called()
        approval.assert_not_called()

        assert repository.load_state(session_id) == state


def test_django_prerequisite_blocks_search_result(runtime):
    app, repository, search, approval = runtime

    approval.side_effect = None

    approval.return_value = EvidenceRequirements(
        evidence_id="E01",
        prerequisites=["E02"],
        player_unlock_verification_required=True,
    )

    with TestClient(app) as client:
        session_id = create_game(client)
        state = collect_evidence(repository, session_id)

        response = client.post(
            url(session_id, "deduction"),
            json=body("deduction", state.revision),
        )

        assert response.status_code == 200

        assert response.json()["sourceIds"] == []
        assert (
            response.json()["status"]
            == "INSUFFICIENT_EVIDENCE"
        )

        search.assert_called_once()
        approval.assert_called_once()


def test_state_change_during_search_returns_conflict(runtime):
    app, repository, search, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = collect_evidence(repository, session_id)

        def change_state(*args, **kwargs):
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

            return []

        search.side_effect = change_state

        response = client.post(
            url(session_id, "assist"),
            json=body("assist", state.revision),
        )

        assert response.status_code == 409

        assert "deduction" not in response.json()
        assert "hint" not in response.json()

        assert (
            repository.load_state(session_id).revision
            == state.revision + 1
        )


# Runtime errors and HTTP status mapping.


@pytest.mark.parametrize(
    "resource",
    [
        "dialogue_resources",
        "django_content_client",
    ],
)
def test_missing_runtime_returns_503(runtime, resource):
    app, repository, search, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = repository.load_state(session_id)

        setattr(app.state, resource, None)

        response = client.post(
            url(session_id, "assist"),
            json=body("assist", state.revision),
        )

        assert response.status_code == 503
        search.assert_not_called()


@pytest.mark.parametrize(
    ("error_type", "status"),
    [
        (MCPToolValidationError, 502),
        (MCPToolExecutionError, 503),
        (MCPToolTimeoutError, 504),
    ],
)
def test_mcp_error_mapping(
    runtime,
    monkeypatch,
    error_type,
    status,
):
    app, repository, _, _ = runtime

    monkeypatch.setattr(
        MCPToolClient,
        "call_tool",
        AsyncMock(
            side_effect=error_type(
                "PRIVATE_HOST SECRET_TOKEN"
            )
        ),
    )

    with TestClient(app) as client:
        session_id = create_game(client)
        state = repository.load_state(session_id)

        response = client.post(
            url(session_id, "hint"),
            json=body("hint", state.revision),
        )

        assert response.status_code == status

        assert "PRIVATE_HOST" not in response.text
        assert "SECRET_TOKEN" not in response.text

        assert repository.load_state(session_id) == state


def test_search_service_failure_is_sanitized(runtime):
    app, repository, search, _ = runtime

    search.side_effect = RuntimeError(
        "INTERNAL_RAG_URL SECRET_TOKEN"
    )

    with TestClient(app) as client:
        session_id = create_game(client)
        state = collect_evidence(repository, session_id)

        response = client.post(
            url(session_id, "assist"),
            json=body("assist", state.revision),
        )

        assert response.status_code == 503

        assert "INTERNAL_RAG_URL" not in response.text
        assert "SECRET_TOKEN" not in response.text

        assert repository.load_state(session_id) == state


# Public response contract.


def test_public_response_fields(runtime):
    app, repository, _, _ = runtime

    with TestClient(app) as client:
        session_id = create_game(client)
        state = collect_evidence(repository, session_id)

        response = client.post(
            url(session_id, "assist"),
            json=body("assist", state.revision),
        )

        assert response.status_code == 200

        data = response.json()

        assert set(data) == {
            "deduction",
            "hint",
            "revision",
        }

        assert set(data["deduction"]) == {
            "agentType",
            "text",
            "sourceIds",
            "status",
            "verdict",
            "contradiction",
            "revision",
        }

        assert set(data["hint"]) == {
            "agentType",
            "text",
            "sourceIds",
            "level",
            "status",
            "chapter",
            "collectedCount",
            "suggestedCharacterId",
            "revision",
        }

        assert (
            data["deduction"]["revision"]
            == data["hint"]["revision"]
            == state.revision
        )


def test_openapi_agent_routes(runtime):
    app, _, _, _ = runtime

    paths = app.openapi()["paths"]

    agent_paths = {
        path
        for path in paths
        if "/agents/" in path
    }

    assert agent_paths == {
        url("{session_id}", endpoint)
        for endpoint in ENDPOINTS
    }

    for path in agent_paths:
        assert "post" in paths[path]

    assert "/api/games/{session_id}/chat" in paths
