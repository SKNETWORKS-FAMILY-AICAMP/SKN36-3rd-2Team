"""Security regression tests for E26-A RAG publication."""

import hashlib

import pytest

from crimescene.api.expanded_rag_binding import (
    resolve_rag_binding,
    validate_e26_rag_publication,
    REVISION2_COLLECTION,
)
from crimescene.ingest.expanded_dataset import (
    DRAFT_FLAG,
    make_extended_document,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GameState
from crimescene.retriever.versioned_retrieval import retrieval_options


ACTION = "ACT_AUDIT_LOG_ACCESS_VERIFIED"


@pytest.fixture
def publication():
    document, policy = make_extended_document(
        "E26",
        {
            "source": {
                "evidence_id": "E26",
                "access_scope": "UNLOCKED_ONLY",
                "title": "Audit Log A",
                "finding_public": "Account attribution test.",
            },
        },
    )

    flags = sorted([DRAFT_FLAG, ACTION])

    document = document.model_copy(update={
        "doc_id": "DOC-1120-E26-A",
        "policy_id": "POL-1120-DOC-E26-A",
        "required_evidence": ["E20", "E26"],
        "required_flags": flags,
    })

    policy = policy.model_copy(update={
        "required_evidence": ["E20", "E26"],
        "required_flags": flags,
    })

    manifest = {
        "approved_evidence": {
            "E20": {},
            "E26": {
                "section_a_content_sha256": (
                    hashlib.sha256(
                        document.body.encode("utf-8")
                    ).hexdigest()
                ),
            },
        },
        "approved_e26_sections": ["A"],
        "rag_binding": {
            "dataset_revision": "revision2",
            "collection": REVISION2_COLLECTION,
            "manifest_sha256": "a" * 64,
        },
    }

    return (
        manifest,
        document,
        policy,
    )


def validate(publication, **changes):
    manifest, document, policy = publication

    validate_e26_rag_publication(
        changes.get("manifest", manifest),
        changes.get("documents", [document]),
        changes.get("cards", []),
        changes.get(
            "policies",
            {document.policy_id: policy},
        ),
    )


def test_valid_section_a_publication(publication):
    validate(publication)


@pytest.mark.parametrize(
    "sections",
    [[], ["B"], ["C"], ["A", "B"], ["A", "C"]],
)
def test_restricted_sections_denied(publication, sections):
    manifest, _, _ = publication
    manifest["approved_e26_sections"] = sections

    with pytest.raises(PermissionError):
        validate(publication)


def test_unreviewed_content_denied(publication):
    manifest, _, _ = publication

    del manifest["approved_evidence"]["E26"][
        "section_a_content_sha256"
    ]

    with pytest.raises(PermissionError):
        validate(publication)


def test_wrong_hash_denied(publication):
    manifest, _, _ = publication

    manifest["approved_evidence"]["E26"][
        "section_a_content_sha256"
    ] = "0" * 64

    with pytest.raises(PermissionError):
        validate(publication)


def test_tampered_body_denied(publication):
    _, doc, _ = publication

    with pytest.raises(PermissionError):
        validate(
            publication,
            documents=[
                doc.model_copy(
                    update={"body": "Unapproved content"}
                )
            ],
        )


def test_multiple_e26_documents_denied(publication):
    _, doc, _ = publication

    with pytest.raises(PermissionError):
        validate(
            publication,
            documents=[
                doc,
                doc.model_copy(
                    update={"doc_id": "DOC-1120-E26-B"}
                ),
            ],
        )


def test_missing_required_flag_denied(publication):
    _, doc, policy = publication

    with pytest.raises(PermissionError):
        validate(
            publication,
            policies={
                doc.policy_id: policy.model_copy(
                    update={"required_flags": [DRAFT_FLAG]}
                ),
            },
        )


def test_shared_policy_denied(publication):
    _, doc, _ = publication

    with pytest.raises(PermissionError):
        validate(
            publication,
            cards=[
                {
                    "id": "UNREVIEWED-CARD",
                    "policy_id": doc.policy_id,
                }
            ],
        )


def test_e26_cannot_bind_revision1(publication, tmp_path):
    manifest, _, _ = publication
    manifest["rag_binding"]["dataset_revision"] = "revision1"

    with pytest.raises(PermissionError):
        resolve_rag_binding(manifest, tmp_path)


def test_e26_cannot_bind_without_manifest(publication, tmp_path):
    manifest, _, _ = publication
    del manifest["rag_binding"]

    with pytest.raises(PermissionError):
        resolve_rag_binding(manifest, tmp_path)


@pytest.mark.parametrize(
    "evidence, flags, allowed",
    [
        ([], [], False),
        (["E20"], [ACTION], False),
        (["E26"], [ACTION], False),
        (["E20", "E26"], [], False),
        (["E20", "E26"], [ACTION], True),
    ],
)
def test_published_policy_access(
    publication,
    evidence,
    flags,
    allowed,
):
    _, doc, policy = publication

    initial = create_initial_state("e26-rag-publication")

    state = GameState.model_validate({
        **initial.model_dump(),
        "content_version": "case001_1120",
        "evidence": {
            eid: {"stage": "found"}
            for eid in evidence
        },
        "flags": flags,
    })

    published = policy.model_copy(update={
        "required_flags": [ACTION],
    })

    evaluator = PolicyEvaluator({
        doc.policy_id: published,
    })

    assert evaluator.is_allowed(
        doc.policy_id,
        state,
    ) is allowed


def test_revision2_rejects_legacy_state():
    state = create_initial_state("legacy-revision2-test")

    with pytest.raises(PermissionError):
        retrieval_options(
            state,
            collection_name=REVISION2_COLLECTION,
        )


def test_revision2_accepts_expanded_state():
    initial = create_initial_state("expanded-revision2-test")

    state = GameState.model_validate({
        **initial.model_dump(),
        "content_version": "case001_1120",
    })

    assert retrieval_options(
        state,
        collection_name=REVISION2_COLLECTION,
    ) == {
        "collection_name": REVISION2_COLLECTION,
    }

# STEP 19-16-6: MCP section security

from types import SimpleNamespace
from unittest.mock import MagicMock

from crimescene.mcp.evidence_tools import (
    select_mcp_evidence_results,
)


def make_mcp_e26_state(evidence=None, flags=None):
    if evidence is None:
        evidence = ["E20", "E26"]

    if flags is None:
        flags = [ACTION]

    initial = create_initial_state("e26-mcp-security")

    return GameState.model_validate({
        **initial.model_dump(),
        "content_version": "case001_1120",
        "evidence": {
            eid: {"stage": "found"}
            for eid in evidence
        },
        "flags": flags,
    })


def make_mcp_publication(publication):
    _, document, policy = publication

    document = document.model_copy(update={
        "required_flags": [ACTION],
    })

    policy = policy.model_copy(update={
        "required_flags": [ACTION],
    })

    return document, PolicyEvaluator({
        document.policy_id: policy,
    })


def call_mcp_selector(document, evaluator, state):
    django = MagicMock()

    django.get_evidence_requirements.return_value = (
        SimpleNamespace(
            evidence_id="E26",
            prerequisites=["E20"],
        )
    )

    result = select_mcp_evidence_results(
        state=state,
        chunks=[
            SimpleNamespace(
                source_type="player_document",
                source_id=document.doc_id,
                content=document.body,
            ),
        ],
        documents=[document],
        django_client=django,
        evaluator=evaluator,
    )

    return result, django


def test_mcp_e26_a_authorized(publication):
    doc, evaluator = make_mcp_publication(publication)

    result, django = call_mcp_selector(
        doc,
        evaluator,
        make_mcp_e26_state(),
    )

    assert len(result["items"]) == 1

    item = result["items"][0]

    assert item["document_id"] == "DOC-1120-E26-A"
    assert item["evidence_ids"] == ["E26"]
    assert item["excerpt"] == doc.body[:400]

    django.get_evidence_requirements.assert_called_once()


@pytest.mark.parametrize(
    "evidence, flags",
    [
        ([], []),
        (["E20"], [ACTION]),
        (["E26"], [ACTION]),
        (["E20", "E26"], []),
    ],
)
def test_mcp_e26_missing_conditions(
    publication,
    evidence,
    flags,
):
    doc, evaluator = make_mcp_publication(publication)

    result, django = call_mcp_selector(
        doc,
        evaluator,
        make_mcp_e26_state(evidence, flags),
    )

    assert result == {"items": []}
    django.get_evidence_requirements.assert_not_called()


@pytest.mark.parametrize(
    "document_id",
    [
        "DOC-1120-E26-B",
        "DOC-1120-E26-C",
        "DOC-1120-E26",
    ],
)
def test_mcp_e26_restricted_document(
    publication,
    document_id,
):
    doc, evaluator = make_mcp_publication(publication)

    result, django = call_mcp_selector(
        doc.model_copy(update={
            "doc_id": document_id,
        }),
        evaluator,
        make_mcp_e26_state(),
    )

    assert result == {"items": []}
    django.get_evidence_requirements.assert_not_called()


def test_mcp_e26_missing_evaluator(publication):
    doc, _ = make_mcp_publication(publication)

    result, _ = call_mcp_selector(
        doc,
        None,
        make_mcp_e26_state(),
    )

    assert result == {"items": []}


def test_mcp_e26_unknown_policy(publication):
    doc, _ = make_mcp_publication(publication)

    result, _ = call_mcp_selector(
        doc,
        PolicyEvaluator({}),
        make_mcp_e26_state(),
    )

    assert result == {"items": []}


def test_mcp_e26_staging_denied(publication):
    _, doc, policy = publication

    result, _ = call_mcp_selector(
        doc,
        PolicyEvaluator({
            doc.policy_id: policy,
        }),
        make_mcp_e26_state(
            flags=[ACTION, DRAFT_FLAG],
        ),
    )

    assert result == {"items": []}


def test_mcp_e26_tampered_body_denied(publication):
    doc, evaluator = make_mcp_publication(publication)

    result, _ = call_mcp_selector(
        doc.model_copy(update={
            "body": "Restricted test content",
        }),
        evaluator,
        make_mcp_e26_state(),
    )

    assert result == {"items": []}


def test_mcp_e26_policy_id_tampering(publication):
    doc, evaluator = make_mcp_publication(publication)

    result, _ = call_mcp_selector(
        doc.model_copy(update={
            "policy_id": "POL-UNAPPROVED",
        }),
        evaluator,
        make_mcp_e26_state(),
    )

    assert result == {"items": []}

# STEP 19-16-6-7: HTTP and MCP integration

import asyncio

from fastapi.testclient import TestClient
from mcp import Client

from crimescene.api.app import create_app
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.mcp.context import BoundMCPContext
from crimescene.mcp.server import create_readonly_mcp_server
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def make_e26_api_rules():
    return {
        f"E{i:02d}": EvidenceRule(
            name=f"Evidence E{i:02d}",
            score=2 if i == 20 else 3,
            holder="C10",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for i in range(1, 31)
    }


@pytest.fixture
def e26_api_runtime(tmp_path, publication):
    repo = SQLiteCase001Repository(
        tmp_path / "e26-api.sqlite3"
    )

    app = create_app(
        repo,
        session_secret="e26-api-test-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"

    doc, evaluator = make_mcp_publication(publication)

    with TestClient(app) as client:
        created = client.post("/api/games")
        assert created.status_code == 201

        sid = created.json()["sessionId"]

        response = client.post(
            f"/api/games/{sid}/prologue/complete"
        )

        assert response.status_code == 200

        before = repo.load_state(sid)

        updated = GameState.model_validate({
            **before.model_dump(),
            "current_chapter": "CH03",
            "unlocked_chapters": ["CH00", "CH01", "CH03"],
            "evidence": {
                "E20": {"stage": "found"},
                "E26": {"stage": "found"},
            },
            "flags": [ACTION],
            "score": 5,
            "revision": before.revision + 1,
        })

        repo.commit_state(
            expected_state=before,
            updated_state=updated,
        )

        app.state.e26_section_a_approved = True

        app.state.dialogue_resources = SimpleNamespace(
            documents=(doc,),
            evaluator=evaluator,
            evidence_rules=make_e26_api_rules(),
            trusted_edges=(),
        )

        yield app, client, repo, sid, doc


def test_e26_http_returns_only_a(e26_api_runtime):
    app, client, repo, sid, doc = e26_api_runtime

    before = repo.load_state(sid)

    response = client.get(
        f"/api/games/{sid}/evidence/E26"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["id"] == "E26"
    assert payload["body"] == doc.body
    assert payload["confirmedRelations"] == []
    assert len(payload["documents"]) == 1
    assert payload["documents"][0]["id"] == doc.doc_id
    assert repo.load_state(sid) == before


def test_e26_http_without_approval(e26_api_runtime):
    app, client, _, sid, _ = e26_api_runtime

    app.state.e26_section_a_approved = False

    assert client.get(
        f"/api/games/{sid}/evidence/E26"
    ).status_code == 404


@pytest.mark.parametrize(
    "document_id",
    [
        "DOC-1120-E26",
        "DOC-1120-E26-B",
        "DOC-1120-E26-C",
    ],
)
def test_e26_http_restricted_document(
    e26_api_runtime,
    document_id,
):
    app, client, _, sid, doc = e26_api_runtime

    app.state.dialogue_resources.documents = (
        doc.model_copy(update={
            "doc_id": document_id,
        }),
    )

    assert client.get(
        f"/api/games/{sid}/evidence/E26"
    ).status_code == 404


def test_e26_http_missing_flag(e26_api_runtime):
    _, client, repo, sid, _ = e26_api_runtime

    before = repo.load_state(sid)

    updated = GameState.model_validate({
        **before.model_dump(),
        "flags": [],
        "revision": before.revision + 1,
    })

    repo.commit_state(
        expected_state=before,
        updated_state=updated,
    )

    assert client.get(
        f"/api/games/{sid}/evidence/E26"
    ).status_code == 404


def test_e26_http_cross_session(e26_api_runtime):
    app, _, _, sid, _ = e26_api_runtime

    with TestClient(app) as stranger:
        assert stranger.get(
            f"/api/games/{sid}/evidence/E26"
        ).status_code == 404


@pytest.mark.parametrize("thumbnail", [False, True])
def test_e26_http_photo_blocked(
    e26_api_runtime,
    monkeypatch,
    tmp_path,
    thumbnail,
):
    _, client, _, sid, _ = e26_api_runtime

    (tmp_path / "E26.png").write_bytes(
        b"restricted original"
    )

    (tmp_path / "E26_thumb.png").write_bytes(
        b"restricted thumbnail"
    )

    monkeypatch.setenv(
        "CRIMESCENE_EVIDENCE_IMAGE_DIR",
        str(tmp_path),
    )

    response = client.get(
        f"/api/games/{sid}/evidence/E26/photo",
        params={"thumbnail": thumbnail},
    )

    assert response.status_code == 404


@pytest.mark.parametrize("verified", [True, False])
def test_e26_mcp_sdk_search(
    e26_api_runtime,
    monkeypatch,
    verified,
):
    app, _, repo, sid, document = e26_api_runtime

    state = repo.load_state(sid)

    if not verified:
        state = GameState.model_validate({
            **state.model_dump(),
            "flags": [],
        })

    evaluator = app.state.dialogue_resources.evaluator
    rules = make_e26_api_rules()

    resources = NPCRAGResources(
        personas={},
        qdrant_client=None,
        neo4j_driver=None,
        embedder=None,
        encoder=None,
        trusted_records=(),
        documents=(document,),
        npc_cards=(),
        registry=(),
        trusted_edges=(),
        evidence_rules=rules,
        evaluator=evaluator,
        content_version="case001_1120",
        collection_name=REVISION2_COLLECTION,
    )

    def mock_search(*args, **kwargs):
        assert kwargs["collection_name"] == REVISION2_COLLECTION

        return [
            SimpleNamespace(
                source_type="player_document",
                source_id=document.doc_id,
                content=document.body,
            )
        ]

    monkeypatch.setattr(
        "crimescene.mcp.server.search_authorized_hybrid_context",
        mock_search,
    )

    django = DjangoContentClient(
        base_url="http://localhost:8001",
        token="x" * 40,
    )

    def mock_requirements(self, case_id, evidence_id):
        assert case_id == "CASE-001"
        assert evidence_id == "E26"

        return SimpleNamespace(
            evidence_id="E26",
            prerequisites=["E20"],
        )

    monkeypatch.setattr(
        DjangoContentClient,
        "get_evidence_requirements",
        mock_requirements,
    )

    context = BoundMCPContext.from_owned_game_state(
        state=state,
        load_state=lambda _: state,
        active_character_id="C01",
    )

    server = create_readonly_mcp_server(
        context=context,
        evidence_rules=rules,
        evaluator=evaluator,
        django_client=django,
        rag_resources=resources,
    )

    async def invoke():
        async with Client(server) as client:
            result = await client.call_tool(
                "search_authorized_evidence",
                {"query": "audit log", "limit": 3},
            )

            assert not result.is_error

            items = result.structured_content["items"]

            if verified:
                assert len(items) == 1
                assert items[0]["document_id"] == document.doc_id
            else:
                assert items == []

    asyncio.run(invoke())

# STEP 19-16-7: STORY_026 prerequisites

from dataclasses import replace

from crimescene.api.story_event_conditions import (
    StoryEventConditions,
    matches_story_event_prerequisites,
)


def make_e26_story_conditions():
    return StoryEventConditions(
        story_id="STORY_026",
        chapter="CH03",
        all_evidence=frozenset({"E20", "E26"}),
        required_flags=frozenset({
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "INF_POST_EVENT_DELETE",
        }),
    )


@pytest.mark.parametrize(
    "flags, expected",
    [
        ([], False),
        (["ACT_AUDIT_LOG_ACCESS_VERIFIED"], False),
        (["INF_POST_EVENT_DELETE"], False),
        ([
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "INF_POST_EVENT_DELETE",
        ], True),
    ],
)
def test_e26_story_required_flags(
    e26_api_runtime,
    flags,
    expected,
):
    _, _, repo, sid, _ = e26_api_runtime

    state = repo.load_state(sid)

    candidate = GameState.model_validate({
        **state.model_dump(),
        "flags": flags,
    })

    assert matches_story_event_prerequisites(
        make_e26_story_conditions(),
        candidate,
    ) is expected

    assert repo.load_state(sid) == state


@pytest.mark.parametrize("missing", ["E20", "E26"])
def test_e26_story_missing_evidence(
    e26_api_runtime,
    missing,
):
    _, _, repo, sid, _ = e26_api_runtime

    state = repo.load_state(sid)
    evidence = state.model_dump()["evidence"]
    evidence.pop(missing)

    candidate = GameState.model_validate({
        **state.model_dump(),
        "evidence": evidence,
        "score": 3 if missing == "E20" else 2,
        "flags": [
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "INF_POST_EVENT_DELETE",
        ],
    })

    assert not matches_story_event_prerequisites(
        make_e26_story_conditions(),
        candidate,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"all_evidence": frozenset({"E26"})},
        {"all_evidence": frozenset({"E20"})},
        {"any_evidence": frozenset({"E26"})},
        {"required_flags": frozenset({
            "ACT_AUDIT_LOG_ACCESS_VERIFIED"
        })},
        {"required_flags": frozenset({
            "INF_POST_EVENT_DELETE"
        })},
        {"chapter": "CH02"},
    ],
)
def test_e26_story_invalid_contract(
    e26_api_runtime,
    overrides,
):
    _, _, repo, sid, _ = e26_api_runtime

    state = repo.load_state(sid)

    candidate = GameState.model_validate({
        **state.model_dump(),
        "flags": [
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "INF_POST_EVENT_DELETE",
        ],
    })

    invalid = replace(
        make_e26_story_conditions(),
        **overrides,
    )

    assert not matches_story_event_prerequisites(
        invalid,
        candidate,
    )

# STEP 19-16-7-5: E26 inference integration

from crimescene.scenario.investigation_progress import (
    InferenceRule,
    submit_inference,
)


def make_e26_inference_rule(**overrides):
    values = {
        "rule_id": "LINK-099",
        "inference_id": "INF_POST_EVENT_DELETE",
        "chapter": "CH03",
        "evidence_ids": frozenset({"E20", "E26"}),
        "required_flags": frozenset({
            "ACT_AUDIT_LOG_ACCESS_VERIFIED"
        }),
    }

    values.update(overrides)

    return InferenceRule(**values)


def post_e26_inference(runtime, evidence=None, **extra):
    app, client, repo, sid, _ = runtime

    return client.post(
        f"/api/games/{sid}/inferences",
        json={
            "evidenceIds": (
                ["E20", "E26"]
                if evidence is None
                else evidence
            ),
            "expectedRevision": repo.load_state(sid).revision,
            **extra,
        },
    )


def test_e26_inference_success(e26_api_runtime):
    app, _, repo, sid, _ = e26_api_runtime

    app.state.approved_inference_rules = (
        make_e26_inference_rule(),
    )

    before = repo.load_state(sid)
    response = post_e26_inference(e26_api_runtime)

    assert response.status_code == 200

    payload = response.json()

    assert payload["accepted"] is True
    assert payload["created"] is True
    assert payload["inferenceIds"] == [
        "INF_POST_EVENT_DELETE"
    ]

    after = repo.load_state(sid)

    assert "INF_POST_EVENT_DELETE" in after.flags
    assert after.revision == before.revision + 1
    assert after.score == before.score
    assert after.evidence == before.evidence


def test_e26_inference_idempotent(e26_api_runtime):
    app, _, repo, sid, _ = e26_api_runtime

    app.state.approved_inference_rules = (
        make_e26_inference_rule(),
    )

    first = post_e26_inference(e26_api_runtime)
    assert first.status_code == 200

    before = repo.load_state(sid)

    repeated = post_e26_inference(e26_api_runtime)

    assert repeated.status_code == 200
    assert repeated.json()["accepted"] is True
    assert repeated.json()["created"] is False
    assert repo.load_state(sid) == before


def test_e26_inference_unapproved_section(e26_api_runtime):
    app, _, repo, sid, _ = e26_api_runtime

    app.state.approved_inference_rules = (
        make_e26_inference_rule(),
    )

    app.state.e26_section_a_approved = False

    before = repo.load_state(sid)

    assert post_e26_inference(
        e26_api_runtime
    ).status_code == 403

    assert repo.load_state(sid) == before


def test_e26_inference_unpublished_rule(e26_api_runtime):
    app, _, repo, sid, _ = e26_api_runtime

    app.state.approved_inference_rules = ()

    before = repo.load_state(sid)
    response = post_e26_inference(e26_api_runtime)

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert response.json()["created"] is False
    assert repo.load_state(sid) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"flags": []},
        {
            "evidence": {"E20": {"stage": "found"}},
            "score": 2,
        },
        {
            "evidence": {"E26": {"stage": "found"}},
            "score": 3,
        },
    ],
)
def test_e26_inference_missing_conditions(
    e26_api_runtime,
    changes,
):
    app, _, repo, sid, _ = e26_api_runtime

    app.state.approved_inference_rules = (
        make_e26_inference_rule(),
    )

    state = repo.load_state(sid)

    updated = GameState.model_validate({
        **state.model_dump(),
        **changes,
        "revision": state.revision + 1,
    })

    repo.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    before = repo.load_state(sid)

    assert post_e26_inference(
        e26_api_runtime
    ).status_code == 403

    assert repo.load_state(sid) == before


def test_e26_inference_wrong_chapter(e26_api_runtime):
    app, _, repo, sid, _ = e26_api_runtime

    app.state.approved_inference_rules = (
        make_e26_inference_rule(),
    )

    state = repo.load_state(sid)

    updated = GameState.model_validate({
        **state.model_dump(),
        "current_chapter": "CH01",
        "revision": state.revision + 1,
    })

    repo.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    before = repo.load_state(sid)
    response = post_e26_inference(e26_api_runtime)

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert repo.load_state(sid) == before


@pytest.mark.parametrize(
    "overrides",
    [
        {"inference_id": "INF_VOICE_TRACE"},
        {"inference_id": "INF_RESPONSIBILITY_2026"},
        {"chapter": "CH02"},
        {"chapter": "CH04"},
        {"evidence_ids": frozenset({"E26", "E29"})},
        {"evidence_ids": frozenset({"E20", "E21"})},
        {"evidence_ids": frozenset({"E20", "E30"})},
        {"required_flags": frozenset()},
        {"required_flags": frozenset({"ACT_OTHER"})},
    ],
)
def test_e26_inference_invalid_contract(overrides):
    with pytest.raises(ValueError):
        make_e26_inference_rule(**overrides)


def test_e26_inference_client_cannot_approve(e26_api_runtime):
    app, _, repo, sid, _ = e26_api_runtime

    app.state.e26_section_a_approved = False

    before = repo.load_state(sid)

    response = post_e26_inference(
        e26_api_runtime,
        e26_section_a_approved=True,
    )

    assert response.status_code == 422
    assert repo.load_state(sid) == before


def test_e26_inference_direct_engine_denied(e26_api_runtime):
    _, _, repo, sid, _ = e26_api_runtime

    state = repo.load_state(sid)

    with pytest.raises(PermissionError):
        submit_inference(
            state,
            evidence_ids=frozenset({"E20", "E26"}),
            rules=(make_e26_inference_rule(),),
        )

    assert repo.load_state(sid) == state

# STEP 19-16-7-6: STORY_026 event integration

from unittest.mock import Mock

from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
    ContentServiceNotFoundError,
)
from crimescene.api.story_event_delivery_gate import (
    StoryEventBinding,
)


E26_TEST_EVENT = "EVT-CH03-026"


@pytest.fixture
def e26_story_runtime(e26_api_runtime):
    app, client, repo, sid, document = e26_api_runtime

    app.state.approved_inference_rules = (
        make_e26_inference_rule(),
    )

    app.state.story_event_bindings = {
        E26_TEST_EVENT: StoryEventBinding(
            source_story_id="STORY_026",
            event_key=E26_TEST_EVENT,
            chapter="CH03",
        ),
    }

    app.state.story_event_conditions = {
        "STORY_026": make_e26_story_conditions(),
    }

    django = Mock(spec=DjangoContentClient)

    django.get_approved_story_event.return_value = (
        ApprovedStoryEvent(
            event_key=E26_TEST_EVENT,
            chapter="CH03",
            trigger_type="EVIDENCE_COLLECTED",
            required_evidence_ids=["E20", "E26"],
            title="Test audit event",
            text="TEST_E26_A_APPROVED_EVENT",
        )
    )

    from crimescene.api.story_event_delivery_gate import (
        story_event_payload_sha256,
    )

    event = django.get_approved_story_event.return_value

    binding = app.state.story_event_bindings[E26_TEST_EVENT]

    app.state.story_event_bindings[E26_TEST_EVENT] = replace(
        binding,
        payload_sha256=story_event_payload_sha256(event),
    )

    app.state.django_content_client = django

    return e26_api_runtime, django


def test_e26_story_queue_after_inference(e26_story_runtime):
    runtime, django = e26_story_runtime
    app, client, repo, sid, _ = runtime

    before = repo.load_state(sid)

    assert "STORY_026" not in before.queued_story_events

    response = post_e26_inference(runtime)

    assert response.status_code == 200
    assert response.json()["created"] is True

    after = repo.load_state(sid)

    assert "INF_POST_EVENT_DELETE" in after.flags
    assert after.queued_story_events.count("STORY_026") == 1
    assert after.revision == before.revision + 1
    assert after.score == before.score
    assert after.evidence == before.evidence

    django.get_approved_story_event.assert_called_once()

    event = client.get(
        f"/api/games/{sid}/story-events/{E26_TEST_EVENT}"
    )

    assert event.status_code == 200
    assert event.json()["text"] == "TEST_E26_A_APPROVED_EVENT"


def test_e26_story_queue_idempotent(e26_story_runtime):
    runtime, django = e26_story_runtime
    _, _, repo, sid, _ = runtime

    assert post_e26_inference(runtime).status_code == 200

    before = repo.load_state(sid)

    django.get_approved_story_event.reset_mock()

    response = post_e26_inference(runtime)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert repo.load_state(sid) == before

    assert before.queued_story_events.count("STORY_026") == 1

    django.get_approved_story_event.assert_not_called()


@pytest.mark.parametrize(
    "error_type",
    [
        ContentServiceNotFoundError,
        ContentServiceError,
    ],
)
def test_e26_story_approval_failure_rolls_back(
    e26_story_runtime,
    error_type,
):
    runtime, django = e26_story_runtime
    _, _, repo, sid, _ = runtime

    django.get_approved_story_event.side_effect = (
        error_type("TEST_APPROVAL_FAILURE")
    )

    before = repo.load_state(sid)

    response = post_e26_inference(runtime)

    assert response.status_code == 503

    after = repo.load_state(sid)

    assert after == before
    assert "INF_POST_EVENT_DELETE" not in after.flags
    assert "STORY_026" not in after.queued_story_events


@pytest.mark.parametrize(
    "required_evidence",
    [
        ["E26"],
        ["E20"],
        ["E20", "E26", "E30"],
    ],
)
def test_e26_story_invalid_django_contract(
    e26_story_runtime,
    required_evidence,
):
    runtime, django = e26_story_runtime
    _, _, repo, sid, _ = runtime

    original = django.get_approved_story_event.return_value

    django.get_approved_story_event.return_value = (
        original.model_copy(update={
            "required_evidence_ids": required_evidence,
        })
    )

    before = repo.load_state(sid)

    response = post_e26_inference(runtime)

    assert response.status_code == 503
    assert repo.load_state(sid) == before


def test_e26_story_cross_session_denied(e26_story_runtime):
    runtime, django = e26_story_runtime
    app, _, repo, sid, _ = runtime

    assert post_e26_inference(runtime).status_code == 200

    before = repo.load_state(sid)

    django.get_approved_story_event.reset_mock()

    with TestClient(app) as stranger:
        response = stranger.get(
            f"/api/games/{sid}/story-events/{E26_TEST_EVENT}"
        )

    assert response.status_code == 404
    assert repo.load_state(sid) == before

    django.get_approved_story_event.assert_not_called()

# STEP 19-16-7-7: Story event release security

from crimescene.api.expanded_progression_runtime import (
    configure_e26_story_event,
)
from crimescene.api.story_event_delivery_gate import (
    select_approved_queued_story_event,
    story_event_payload_sha256,
)


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "UNREVIEWED_REPLACEMENT"},
        {"title": "UNREVIEWED_TITLE"},
        {"required_evidence_ids": ["E26"]},
    ],
)
def test_e26_story_payload_tampering(
    e26_story_runtime,
    changes,
):
    runtime, django = e26_story_runtime
    app, _, repo, sid, _ = runtime

    assert post_e26_inference(runtime).status_code == 200

    state = repo.load_state(sid)
    binding = app.state.story_event_bindings[E26_TEST_EVENT]

    event = django.get_approved_story_event.return_value

    assert select_approved_queued_story_event(
        state=state,
        binding=binding,
        approved_event=event,
    ) is not None

    modified = event.model_copy(update=changes)

    assert select_approved_queued_story_event(
        state=state,
        binding=binding,
        approved_event=modified,
    ) is None

    assert repo.load_state(sid) == state


@pytest.mark.parametrize(
    "flag",
    [
        "ACT_AUDIT_LOG_ACCESS_VERIFIED",
        "INF_POST_EVENT_DELETE",
    ],
)
def test_e26_story_delivery_missing_flag(
    e26_story_runtime,
    flag,
):
    runtime, django = e26_story_runtime
    app, _, repo, sid, _ = runtime

    assert post_e26_inference(runtime).status_code == 200

    state = repo.load_state(sid)

    candidate = GameState.model_validate({
        **state.model_dump(),
        "flags": [
            item for item in state.flags
            if item != flag
        ],
    })

    assert select_approved_queued_story_event(
        state=candidate,
        binding=app.state.story_event_bindings[E26_TEST_EVENT],
        approved_event=django.get_approved_story_event.return_value,
    ) is None


def make_e26_story_manifest(event):
    return {
        "content_version": "case001_1120",
        "scope": "LOCAL_INTEGRATION_TEST",
        "approved_e26_sections": ["A"],
        "approved_e26_inference": True,
        "approved_e26_story_event": {
            "source_story_id": "STORY_026",
            "event_key": event.event_key,
            "chapter": "CH03",
            "section": "A",
            "payload_sha256": story_event_payload_sha256(event),
        },
    }


def test_e26_story_release_binding(e26_story_runtime):
    runtime, django = e26_story_runtime
    app, _, _, _, _ = runtime

    event = django.get_approved_story_event.return_value

    app.state.story_event_bindings = {}
    app.state.story_event_conditions = {}

    manifest = make_e26_story_manifest(event)

    configure_e26_story_event(
        app=app,
        manifest=manifest,
    )

    binding = app.state.story_event_bindings[E26_TEST_EVENT]

    assert binding.source_story_id == "STORY_026"
    assert binding.payload_sha256 == story_event_payload_sha256(event)

    assert (
        app.state.story_event_conditions["STORY_026"]
        == make_e26_story_conditions()
    )


@pytest.mark.parametrize(
    "reason",
    [
        "unapproved_inference",
        "wrong_section",
        "wrong_hash",
        "missing_contract",
    ],
)
def test_e26_story_invalid_release(
    e26_story_runtime,
    reason,
):
    runtime, django = e26_story_runtime
    app, _, _, _, _ = runtime

    event = django.get_approved_story_event.return_value

    app.state.story_event_bindings = {}
    app.state.story_event_conditions = {}

    manifest = make_e26_story_manifest(event)

    if reason == "unapproved_inference":
        manifest["approved_e26_inference"] = False

    elif reason == "wrong_section":
        manifest["approved_e26_sections"] = ["A", "B"]

    elif reason == "wrong_hash":
        manifest["approved_e26_story_event"]["payload_sha256"] = "0" * 64

    elif reason == "missing_contract":
        manifest.pop("approved_e26_story_event")

    with pytest.raises(PermissionError):
        configure_e26_story_event(
            app=app,
            manifest=manifest,
        )

    assert app.state.story_event_bindings == {}
    assert app.state.story_event_conditions == {}

# STEP 19-16-8: E26 follow-up evidence integration

from crimescene.scenario.content_compiler import proposed_routes
from crimescene.api.expanded_investigation_runtime import (
    validate_e26_followup_contract,
)
from crimescene.api.investigation_http import ACTION_CANDIDATES


@pytest.fixture(params=["E27", "E29"])
def e26_followup_runtime(e26_api_runtime, request):
    runtime = e26_api_runtime
    app, client, repo, sid, _ = runtime

    eid = request.param
    action_id = f"inspect-{eid.lower()}-a"
    action = ACTION_CANDIDATES[action_id]

    app.state.approved_investigation_actions = frozenset({
        action_id,
    })

    app.state.approved_acquisition_routes = {
        eid: proposed_routes(eid, action.chapter),
    }

    app.state.investigation_release_version = "v0.12.0"

    django = Mock(spec=DjangoContentClient)

    django.get_player_scene.return_value = SimpleNamespace(
        scene_id=action.scene_id,
        chapter=action.chapter,
    )

    django.get_evidence_requirements.return_value = SimpleNamespace(
        evidence_id=eid,
        prerequisites=sorted(action.required_evidence),
    )

    app.state.django_content_client = django

    before = repo.load_state(sid)

    ids = {"E20", "E26"} | set(action.required_evidence)

    rules = app.state.dialogue_resources.evidence_rules

    updated = GameState.model_validate({
        **before.model_dump(),
        "current_chapter": action.chapter,
        "unlocked_chapters": [
            "CH00", "CH01", "CH02", "CH03", "CH04",
        ],
        "evidence": {
            item: {"stage": "found"}
            for item in ids
        },
        "flags": [
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "INF_POST_EVENT_DELETE",
        ],
        "score": sum(rules[item].score for item in ids),
        "revision": before.revision + 1,
    })

    repo.commit_state(
        expected_state=before,
        updated_state=updated,
    )

    return runtime, eid, action_id, action, django


def post_e26_followup(fixture):
    runtime, eid, action_id, action, django = fixture
    _, client, repo, sid, _ = runtime

    return client.post(
        f"/api/games/{sid}/investigations/{action_id}",
        json={
            "expectedRevision": repo.load_state(sid).revision,
        },
    )


def test_e26_followup_acquisition_success(e26_followup_runtime):
    runtime, eid, _, action, django = e26_followup_runtime
    _, _, repo, sid, _ = runtime

    before = repo.load_state(sid)

    response = post_e26_followup(e26_followup_runtime)

    assert response.status_code == 200, response.text
    assert response.json()["created"] is True

    after = repo.load_state(sid)

    assert after.evidence[eid].stage == "found"
    assert after.score == before.score + 3
    assert after.revision == before.revision + 1
    assert action.action_flag in after.flags

    django.get_player_scene.assert_called_once_with(
        "CASE-001",
        action.scene_id,
        investigation_release="v0.12.0",
    )


def test_e26_followup_idempotent(e26_followup_runtime):
    runtime, eid, _, _, _ = e26_followup_runtime
    _, _, repo, sid, _ = runtime

    assert post_e26_followup(
        e26_followup_runtime
    ).status_code == 200

    before = repo.load_state(sid)

    response = post_e26_followup(e26_followup_runtime)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert repo.load_state(sid) == before


@pytest.mark.parametrize(
    "missing_flag",
    [
        "ACT_AUDIT_LOG_ACCESS_VERIFIED",
        "INF_POST_EVENT_DELETE",
    ],
)
def test_e26_followup_missing_flag(
    e26_followup_runtime,
    missing_flag,
):
    runtime, _, _, _, django = e26_followup_runtime
    _, _, repo, sid, _ = runtime

    before = repo.load_state(sid)

    updated = GameState.model_validate({
        **before.model_dump(),
        "flags": [
            flag for flag in before.flags
            if flag != missing_flag
        ],
        "revision": before.revision + 1,
    })

    repo.commit_state(
        expected_state=before,
        updated_state=updated,
    )

    assert post_e26_followup(
        e26_followup_runtime
    ).status_code == 403

    assert repo.load_state(sid) == updated

    django.get_player_scene.assert_not_called()


@pytest.mark.parametrize(
    "missing",
    ["E20", "E26", "other"],
)
def test_e26_followup_missing_evidence(
    e26_followup_runtime,
    missing,
):
    runtime, _, _, action, django = e26_followup_runtime
    app, _, repo, sid, _ = runtime

    before = repo.load_state(sid)

    eid = (
        next(iter(action.required_evidence - {"E26"}))
        if missing == "other"
        else missing
    )

    evidence = before.model_dump()["evidence"]
    evidence.pop(eid)

    updated = GameState.model_validate({
        **before.model_dump(),
        "evidence": evidence,
        "score": (
            before.score
            - app.state.dialogue_resources.evidence_rules[eid].score
        ),
        "revision": before.revision + 1,
    })

    repo.commit_state(
        expected_state=before,
        updated_state=updated,
    )

    assert post_e26_followup(
        e26_followup_runtime
    ).status_code == 403

    assert repo.load_state(sid) == updated

    django.get_player_scene.assert_not_called()


def test_e26_followup_missing_approval(e26_followup_runtime):
    runtime, _, _, _, django = e26_followup_runtime
    app, _, repo, sid, _ = runtime

    app.state.e26_section_a_approved = False

    before = repo.load_state(sid)

    assert post_e26_followup(
        e26_followup_runtime
    ).status_code == 403

    assert repo.load_state(sid) == before

    django.get_player_scene.assert_not_called()


def test_e26_followup_unpublished_action(e26_followup_runtime):
    runtime, _, _, _, django = e26_followup_runtime
    app, _, repo, sid, _ = runtime

    app.state.approved_investigation_actions = frozenset()

    before = repo.load_state(sid)

    assert post_e26_followup(
        e26_followup_runtime
    ).status_code == 404

    assert repo.load_state(sid) == before

    django.get_player_scene.assert_not_called()


def test_e26_followup_invalid_django_contract(e26_followup_runtime):
    runtime, _, _, _, django = e26_followup_runtime
    _, _, repo, sid, _ = runtime

    django.get_evidence_requirements.return_value.prerequisites = []

    before = repo.load_state(sid)

    assert post_e26_followup(
        e26_followup_runtime
    ).status_code == 503

    assert repo.load_state(sid) == before


def test_e26_followup_django_denied(e26_followup_runtime):
    runtime, _, _, _, django = e26_followup_runtime
    _, _, repo, sid, _ = runtime

    django.get_player_scene.side_effect = (
        ContentServiceNotFoundError("TEST_NOT_APPROVED")
    )

    before = repo.load_state(sid)

    assert post_e26_followup(
        e26_followup_runtime
    ).status_code == 404

    assert repo.load_state(sid) == before


def test_e26_followup_release_contract(e26_followup_runtime):
    _, eid, action_id, action, _ = e26_followup_runtime

    manifest = {
        "approved_e26_sections": ["A"],
        "approved_e26_inference": True,
        "approved_evidence": {
            item: {}
            for item in {"E20", "E26"} | set(action.required_evidence)
        },
        "approved_investigation_actions": {
            action_id: {
                "evidence_id": eid,
                "scene_id": action.scene_id,
                "chapter": action.chapter,
                "route_ids": sorted(action.route_ids),
                "required_flags": sorted(action.required_flags),
                "character_id": None,
            },
        },
    }

    manifest["approved_evidence"][eid] = {
        "score": 3,
        "required_evidence": sorted(action.required_evidence),
    }

    validate_e26_followup_contract(manifest)

    manifest["approved_e26_inference"] = False

    with pytest.raises(PermissionError):
        validate_e26_followup_contract(manifest)
