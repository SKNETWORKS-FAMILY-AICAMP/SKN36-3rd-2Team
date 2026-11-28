"""이슈 #230 - 승인 릴리스 기반 확장판 판정 원장 검증."""

import re

from collections.abc import Mapping
from pathlib import Path

from crimescene.scenario.expanded_ending import ExpandedCaseTruth
from crimescene.scenario.loaders.expanded_case_truth_loader import (
    load_expanded_case_truth,
)


APPROVAL_FIELDS = frozenset({
    "status",
    "content_version",
    "release_version",
    "access_scope",
    "sha256",
})


def load_approved_expanded_truth(
    *,
    manifest: Mapping,
    release_version: str,
    truth_path: Path,
) -> ExpandedCaseTruth:
    """기존 릴리스 검증을 통과한 Manifest만 사용한다."""

    if not isinstance(manifest, Mapping):
        raise TypeError("Invalid release manifest")

    if (
        not isinstance(release_version, str)
        or re.fullmatch(
            r"v[0-9]+\.[0-9]+\.[0-9]+",
            release_version,
        ) is None
    ):
        raise ValueError("Invalid truth release version")

    if (
        manifest.get("case_id") != "CASE-001"
        or manifest.get("content_version") != "case001_1120"
        or manifest.get("scope") != "LOCAL_INTEGRATION_TEST"
    ):
        raise PermissionError("Invalid truth release identity")

    approval = manifest.get("approved_truth")

    if not isinstance(approval, dict):
        raise PermissionError("Expanded truth approval unavailable")

    if set(approval) != APPROVAL_FIELDS:
        raise PermissionError("Invalid expanded truth approval")

    if (
        approval["status"] != "APPROVED"
        or approval["content_version"] != "case001_1120"
        or approval["release_version"] != release_version
        or approval["access_scope"] != "ENGINE_ONLY"
    ):
        raise PermissionError("Invalid expanded truth approval")

    truth = load_expanded_case_truth(
        truth_path,
        expected_sha256=approval["sha256"],
    )

    approved_evidence = manifest.get("approved_evidence")

    if (
        not isinstance(approved_evidence, dict)
        or not approved_evidence
    ):
        raise PermissionError("Evidence approval unavailable")

    progression = manifest.get("approved_progression")

    if not isinstance(progression, dict):
        raise PermissionError("Progression approval unavailable")

    inferences = progression.get("inferences")

    if not isinstance(inferences, dict):
        raise PermissionError("Inference approval unavailable")

    approved_flags = set()

    for item in inferences.values():
        if not isinstance(item, dict):
            raise PermissionError("Invalid inference approval")

        flag = item.get("inference_id")

        if (
            not isinstance(flag, str)
            or re.fullmatch(r"INF_[A-Z0-9_]+", flag) is None
        ):
            raise PermissionError("Invalid inference approval")

        approved_flags.add(flag)

    for axis in truth.proof_axes:
        if not set(axis.required_flags).issubset(approved_flags):
            raise PermissionError("Unapproved proof inference")

        for option in axis.evidence_options:
            if not set(option).issubset(approved_evidence):
                raise PermissionError("Unapproved proof evidence")

            if "E26" in option:
                if (
                    manifest.get("approved_e26_sections") != ["A"]
                    or manifest.get("approved_e26_inference") is not True
                ):
                    raise PermissionError(
                        "Protected proof approval unavailable"
                    )

    return truth



def configure_expanded_truth(
    *,
    app,
    manifest: Mapping,
    release_version: str,
    truth_path: Path,
    required: bool,
) -> bool:
    """승인된 원장만 서버 판정 엔진에 등록한다."""

    if type(required) is not bool:
        raise TypeError("Invalid truth requirement")

    # 이전 초기화에서 남은 원장을 재사용하지 않는다.
    if hasattr(app.state, "case_truth"):
        del app.state.case_truth

    if not isinstance(manifest, Mapping):
        raise TypeError("Invalid release manifest")

    if (
        manifest.get("case_id") != "CASE-001"
        or manifest.get("content_version") != "case001_1120"
        or manifest.get("scope") != "LOCAL_INTEGRATION_TEST"
    ):
        raise PermissionError("Invalid truth release identity")

    if "approved_truth" not in manifest:
        if required:
            raise PermissionError(
                "Expanded truth approval required"
            )

        print("EXPANDED TRUTH: NOT APPROVED")
        return False

    # 승인이 존재하지만 유효하지 않은 경우에는
    # 개발 모드에서도 절대 무시하지 않는다.
    truth = load_approved_expanded_truth(
        manifest=manifest,
        release_version=release_version,
        truth_path=truth_path,
    )

    app.state.case_truth = truth

    print("EXPANDED TRUTH: VERIFIED")
    return True
