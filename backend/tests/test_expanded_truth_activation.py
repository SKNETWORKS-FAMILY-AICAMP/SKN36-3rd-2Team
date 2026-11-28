"""이슈 #230 - 확장판 원장 활성화 및 실패 정책 검증."""

import pytest

from fastapi import FastAPI

from crimescene.api.expanded_truth_runtime import (
    configure_expanded_truth,
)
from crimescene.scenario.expanded_ending import (
    ExpandedCaseTruth,
)

from test_expanded_case_truth_loader import (
    synthetic_truth,
    write_truth,
)


RELEASE = "v9.9.9"


@pytest.fixture
def activation(tmp_path, synthetic_truth):
    path, digest = write_truth(
        tmp_path,
        synthetic_truth,
    )

    manifest = {
        "case_id": "CASE-001",
        "content_version": "case001_1120",
        "scope": "LOCAL_INTEGRATION_TEST",
        "approved_evidence": {
            f"E{i:02d}": {}
            for i in range(1, 30)
        },
        "approved_progression": {
            "inferences": {},
        },
        "approved_truth": {
            "status": "APPROVED",
            "content_version": "case001_1120",
            "release_version": RELEASE,
            "access_scope": "ENGINE_ONLY",
            "sha256": digest,
        },
    }

    return FastAPI(), manifest, path


def activate(env, required=False):
    app, manifest, path = env

    return configure_expanded_truth(
        app=app,
        manifest=manifest,
        release_version=RELEASE,
        truth_path=path,
        required=required,
    )


def test_activate_approved_truth(activation):
    app, _, _ = activation

    assert activate(activation) is True

    assert isinstance(
        app.state.case_truth,
        ExpandedCaseTruth,
    )


def test_development_without_approval(activation):
    app, manifest, _ = activation

    manifest.pop("approved_truth")

    assert activate(activation) is False
    assert not hasattr(app.state, "case_truth")


def test_required_mode_without_approval(activation):
    app, manifest, _ = activation

    manifest.pop("approved_truth")

    with pytest.raises(PermissionError):
        activate(activation, required=True)

    assert not hasattr(app.state, "case_truth")


def test_required_mode_with_approval(activation):
    assert activate(
        activation,
        required=True,
    ) is True


@pytest.mark.parametrize(
    "mode",
    [
        "draft",
        "release",
        "version",
        "scope",
        "evidence",
        "checksum",
        "null_approval",
    ],
)
def test_invalid_approval_always_denied(
    activation,
    mode,
):
    app, manifest, path = activation

    approval = manifest["approved_truth"]

    if mode == "draft":
        approval["status"] = "REVIEW_REQUIRED"

    elif mode == "release":
        approval["release_version"] = "v1.0.0"

    elif mode == "version":
        approval["content_version"] = "case001_v7_1"

    elif mode == "scope":
        approval["access_scope"] = "PUBLIC"

    elif mode == "evidence":
        manifest["approved_evidence"].pop("E01")

    elif mode == "checksum":
        path.write_bytes(path.read_bytes() + b" ")

    elif mode == "null_approval":
        manifest["approved_truth"] = None

    with pytest.raises(PermissionError):
        activate(activation, required=False)

    assert not hasattr(app.state, "case_truth")


def test_missing_approved_file_denied(activation):
    app, _, path = activation

    path.unlink()

    with pytest.raises(FileNotFoundError):
        activate(activation)

    assert not hasattr(app.state, "case_truth")


def test_previous_truth_removed_on_failure(activation):
    app, manifest, _ = activation

    assert activate(activation) is True

    manifest.pop("approved_truth")

    with pytest.raises(PermissionError):
        activate(activation, required=True)

    assert not hasattr(app.state, "case_truth")


def test_previous_truth_not_reused(activation):
    app, manifest, _ = activation

    assert activate(activation) is True

    manifest.pop("approved_truth")

    assert activate(activation) is False
    assert not hasattr(app.state, "case_truth")
