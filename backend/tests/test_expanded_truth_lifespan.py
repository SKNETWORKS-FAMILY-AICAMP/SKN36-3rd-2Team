"""이슈 #230 - 실제 확장판 Lifespan 판정 원장 통합 검증."""

import importlib.util

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import dotenv
import pytest

from fastapi.testclient import TestClient

from crimescene.scenario.content_compiler import (
    PROPOSED_SCORES,
)
from crimescene.scenario.expanded_ending import (
    ExpandedCaseTruth,
)
from crimescene.scenario.schemas.evidence import (
    EvidenceRule,
)

from test_expanded_case_truth_loader import (
    synthetic_truth,
    write_truth,
)

from test_expanded_ending_http import (
    prepare,
    reconstruct,
    accuse,
    ending,
)


RELEASE_VERSION = "v9.9.9"


@pytest.fixture
def expanded_runtime(
    tmp_path,
    monkeypatch,
    synthetic_truth,
):
    """실제 진입점과 격리된 외부 서비스 Fixture를 구성한다."""

    monkeypatch.setenv(
        "CRIMESCENE_SESSION_SECRET",
        "test-only-lifespan-" + "x" * 40,
    )

    monkeypatch.setenv(
        "CRIMESCENE_EXPANDED_DB_PATH",
        str(tmp_path / "game.sqlite3"),
    )

    monkeypatch.setenv(
        "CRIMESCENE_EXPANDED_RELEASE_VERSION",
        RELEASE_VERSION,
    )

    monkeypatch.setenv(
        "CRIMESCENE_E30_CONSENT_REVIEW_VERSION",
        "",
    )

    monkeypatch.setenv(
        "CRIMESCENE_COOKIE_SECURE",
        "false",
    )

    monkeypatch.setenv(
        "CRIMESCENE_REQUIRE_EXPANDED_TRUTH",
        "false",
    )

    # 개발자의 실제 .env를 테스트 환경에 로딩하지 않는다.
    monkeypatch.setattr(
        dotenv,
        "load_dotenv",
        lambda *args, **kwargs: False,
    )

    main_path = (
        Path(__file__).resolve().parents[1]
        / "src/crimescene/api/expanded_main.py"
    )

    spec = importlib.util.spec_from_file_location(
        "_isolated_expanded_truth_main",
        main_path,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 실제 서비스 토큰이 아닌 테스트 전용 값이다.
    token_path = tmp_path / "service-token.txt"

    token_path.write_text(
        "test-only-" + "x" * 40,
        encoding="utf-8",
    )

    truth_path, digest = write_truth(
        tmp_path,
        synthetic_truth,
    )

    monkeypatch.setattr(
        module,
        "TOKEN_PATH",
        token_path,
    )

    monkeypatch.setattr(
        module,
        "TRUTH_PATH",
        truth_path,
    )

    legacy = dict(zip(
        [f"E{i:02d}" for i in range(1, 11)],
        [1, 2, 3, 2, 3, 3, 2, 2, 1, 2],
        strict=True,
    ))

    rules = {
        eid: EvidenceRule(
            name=f"Test {eid}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for eid, score in {
            **legacy,
            **PROPOSED_SCORES,
        }.items()
    }

    manifest = {
        "case_id": "CASE-001",
        "content_version": "case001_1120",
        "scope": "LOCAL_INTEGRATION_TEST",
        "approved_evidence": {
            eid: {}
            for eid in rules
            if eid != "E30"
        },
        "approved_progression": {
            "inferences": {},
        },
        "approved_truth": {
            "status": "APPROVED",
            "content_version": "case001_1120",
            "release_version": RELEASE_VERSION,
            "access_scope": "ENGINE_ONLY",
            "sha256": digest,
        },
    }

    closed = []

    @contextmanager
    def fake_resources(**kwargs):
        assert kwargs["release_version"] == RELEASE_VERSION

        try:
            yield SimpleNamespace(
                content_version="case001_1120",
                evidence_rules=rules,
                evaluator=SimpleNamespace(
                    snapshot_policies=lambda: {},
                ),
            )
        finally:
            closed.append("resources")

    @contextmanager
    def fake_django(**kwargs):
        try:
            yield SimpleNamespace()
        finally:
            closed.append("django")

    monkeypatch.setattr(
        module,
        "load_expanded_release_resources",
        fake_resources,
    )

    monkeypatch.setattr(
        module,
        "DjangoContentClient",
        fake_django,
    )

    monkeypatch.setattr(
        module,
        "configure_published_investigations",
        lambda **kwargs: manifest,
    )

    for name in (
        "configure_published_npc_acquisitions",
        "configure_published_progression",
        "configure_expanded_chapters",
    ):
        monkeypatch.setattr(
            module,
            name,
            lambda **kwargs: None,
        )

    return SimpleNamespace(
        module=module,
        app=module.app,
        repository=module.repository,
        manifest=manifest,
        truth_path=truth_path,
        truth_payload=synthetic_truth,
        rules=rules,
        closed=closed,
    )


def create_game(env, client):
    response = client.post("/api/games")

    assert response.status_code == 201, response.text

    sid = response.json()["sessionId"]

    response = client.post(
        f"/api/games/{sid}/prologue/complete"
    )

    assert response.status_code == 200

    runtime = (
        env.app,
        client,
        env.repository,
        sid,
        env.rules,
    )

    # 실제 스토리 정본 대신 최종 판정 테스트용
    # 증거 및 CH04 상태를 구성한다.
    prepare(runtime)

    return runtime


def selections_for(env):
    return {
        item["axis"]: item["evidence_options"][0]
        for item in env.truth_payload["proof_axes"]
    }


def assert_shutdown(env):
    assert env.app.state.expanded_runtime_ready is False

    assert not hasattr(
        env.app.state,
        "case_truth",
    )

    assert not hasattr(
        env.app.state,
        "expanded_truth_ready",
    )

    assert sorted(env.closed) == [
        "django",
        "resources",
    ]


def test_lifespan_approved_truth_and_ending(
    expanded_runtime,
    monkeypatch,
):
    env = expanded_runtime

    monkeypatch.setenv(
        "CRIMESCENE_REQUIRE_EXPANDED_TRUTH",
        "true",
    )

    with TestClient(env.app) as client:
        assert env.app.state.expanded_runtime_ready is True
        assert env.app.state.expanded_truth_ready is True

        assert isinstance(
            env.app.state.case_truth,
            ExpandedCaseTruth,
        )

        runtime = create_game(env, client)

        response = reconstruct(
            runtime,
            selections_for(env),
        )

        assert response.status_code == 200, response.text
        assert response.json()["accepted"] is True
        assert response.json()["created"] is True

        response = accuse(runtime, "C02")

        assert response.status_code == 200, response.text
        assert response.json()["result"] == "CORRECT"

        result = ending(runtime)

        assert result["outcome"] == "FULL"
        assert result["truth"]["perpetratorId"] == "C02"

    assert_shutdown(env)


def test_lifespan_development_without_approval(
    expanded_runtime,
):
    env = expanded_runtime

    env.manifest.pop("approved_truth")

    with TestClient(env.app) as client:
        assert env.app.state.expanded_runtime_ready is True
        assert env.app.state.expanded_truth_ready is False

        assert not hasattr(
            env.app.state,
            "case_truth",
        )

        runtime = create_game(env, client)

        _, _, repository, sid, _ = runtime

        before = repository.load_state(sid)

        response = reconstruct(
            runtime,
            selections_for(env),
        )

        assert response.status_code == 503
        assert accuse(runtime).status_code == 503

        assert repository.load_state(sid) == before

    assert_shutdown(env)


@pytest.mark.parametrize(
    ("mode", "error_type"),
    [
        ("required_missing", PermissionError),
        ("invalid_status", PermissionError),
        ("wrong_release", PermissionError),
        ("missing_file", FileNotFoundError),
        ("modified_file", PermissionError),
        ("invalid_mode", ValueError),
        ("unapproved_inference", PermissionError),
        ("missing_progression", PermissionError),
        ("invalid_inference", PermissionError),
        ("protected_e26", PermissionError),
    ],
)
def test_lifespan_rejects_invalid_truth(
    expanded_runtime,
    monkeypatch,
    tmp_path,
    mode,
    error_type,
):
    env = expanded_runtime

    approval = env.manifest["approved_truth"]

    if mode == "required_missing":
        monkeypatch.setenv(
            "CRIMESCENE_REQUIRE_EXPANDED_TRUTH",
            "true",
        )

        env.manifest.pop("approved_truth")

    elif mode == "invalid_status":
        approval["status"] = "REVIEW_REQUIRED"

    elif mode == "wrong_release":
        approval["release_version"] = "v1.0.0"

    elif mode == "missing_file":
        env.truth_path.unlink()

    elif mode == "modified_file":
        env.truth_path.write_bytes(
            env.truth_path.read_bytes() + b" "
        )

    elif mode == "invalid_mode":
        monkeypatch.setenv(
            "CRIMESCENE_REQUIRE_EXPANDED_TRUTH",
            "invalid",
        )

    elif mode == "unapproved_inference":
        env.truth_payload["proof_axes"][0][
            "required_flags"
        ] = ["INF_TEST_UNAPPROVED"]

        _, digest = write_truth(
            tmp_path,
            env.truth_payload,
        )

        approval["sha256"] = digest

    elif mode == "missing_progression":
        env.manifest.pop("approved_progression")

    elif mode == "invalid_inference":
        env.manifest["approved_progression"][
            "inferences"
        ] = {
            "LINK-001": {
                "inference_id": "INVALID",
            },
        }

    elif mode == "protected_e26":
        env.truth_payload["proof_axes"][3][
            "evidence_options"
        ] = [["E20", "E26"]]

        _, digest = write_truth(
            tmp_path,
            env.truth_payload,
        )

        approval["sha256"] = digest

    with pytest.raises(error_type):
        with TestClient(env.app):
            pytest.fail(
                "Invalid runtime must not start"
            )

    assert_shutdown(env)
