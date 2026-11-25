"""Local integration chapter policy for CASE-001 v0.15.0."""

import hashlib
import json
from types import MappingProxyType

from crimescene.scenario.chapter_progress import ChapterUnlockRule

VERSION = "case001_1120"
RELEASE = "v0.15.0"

# Bind the local policy to the verified immutable release.
MANIFEST_SHA256 = (
    "dfc2e83129875cf643d89b67d0f99398b"
    "5846324bf875f992f4663155d69f65b"
)

BRANCH_REQUIREMENTS = frozenset({"E11", "E19", "E20"})

FINAL_REQUIREMENTS = frozenset({
    "E17", "E20", "E26", "E27", "E28",
})

FINAL_FLAGS = frozenset({
    "ACT_AUDIT_LOG_ACCESS_VERIFIED",
    "INF_POST_EVENT_DELETE",
    "ACT_ACCOUNTING_VERSIONS_COMPARED",
})


def build_expanded_chapter_rules():
    """Construct immutable server-side chapter rules."""

    return MappingProxyType({
        "CH01": ChapterUnlockRule(
            target_chapter="CH01",
            requires_completed_prologue=True,
        ),
        "CH02": ChapterUnlockRule(
            target_chapter="CH02",
            required_evidence=BRANCH_REQUIREMENTS,
        ),
        "CH03": ChapterUnlockRule(
            target_chapter="CH03",
            required_evidence=BRANCH_REQUIREMENTS,
        ),
        "CH04": ChapterUnlockRule(
            target_chapter="CH04",
            required_evidence=FINAL_REQUIREMENTS,
            required_flags=FINAL_FLAGS,
        ),
    })


def configure_expanded_chapters(
    *,
    app,
    manifest,
    release_version,
):
    """Reject unverified release/chapter policy combinations."""

    if release_version != RELEASE:
        if manifest.get("approved_e26_inference") is True:
            raise PermissionError(
                "Chapter policy unavailable for release"
            )

        # Preserve previous releases without enabling new rules.
        return

    if (
        manifest.get("case_id") != "CASE-001"
        or manifest.get("content_version") != VERSION
        or manifest.get("scope") != "LOCAL_INTEGRATION_TEST"
        or manifest.get("approved_e26_sections") != ["A"]
        or manifest.get("approved_e26_inference") is not True
    ):
        raise PermissionError("Invalid chapter release contract")

    checksum = hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    if checksum != MANIFEST_SHA256:
        raise PermissionError("Chapter release checksum mismatch")

    approved = manifest.get("approved_evidence")

    if not isinstance(approved, dict):
        raise TypeError("Approved evidence unavailable")

    if not (
        BRANCH_REQUIREMENTS | FINAL_REQUIREMENTS
    ).issubset(approved):
        raise PermissionError("Chapter evidence not published")

    if {"E07", "E30"}.intersection(approved):
        raise PermissionError("Protected evidence published")

    if app.state.e26_section_a_approved is not True:
        raise PermissionError("E26 section A not approved")

    app.state.chapter_unlock_rules = build_expanded_chapter_rules()

    print(
        "APPROVED CHAPTER RULES:",
        sorted(app.state.chapter_unlock_rules),
    )
    print("INVESTIGATION BRANCH REVISITS: ENABLED")
