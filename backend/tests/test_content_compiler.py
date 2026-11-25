
"""Issue #165 - content compilation validation."""

import pytest

from crimescene.scenario.content_compiler import (
    ALL_IDS,
    EXTENDED_IDS,
    LEGACY_IDS,
    PROPOSED_SCORES,
    compile_evidence,
    proposed_routes,
    validate_unique_ids,
)
from crimescene.scenario.schemas.evidence import EvidenceRule


@pytest.fixture
def legacy_rules():
    return {
        eid: EvidenceRule(
            name=f"Test {eid}",
            score=1,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=["Test question"],
        )
        for eid in sorted(LEGACY_IDS)
    }


@pytest.fixture
def extended_rows():
    return [
        {
            "evidence_id": eid,
            "title": f"Test {eid}",
            "holder_npc_id": "C01",
            "chapter": "CH02",
            "access_scope": "UNLOCKED_ONLY",
        }
        for eid in sorted(EXTENDED_IDS)
    ]


def test_compile_all_evidence(legacy_rules, extended_rows):
    result = compile_evidence(legacy_rules, extended_rows)

    assert set(result) == ALL_IDS
    assert len(result) == 30


def test_new_evidence_denied_by_default(
    legacy_rules,
    extended_rows,
):
    result = compile_evidence(legacy_rules, extended_rows)

    for eid in EXTENDED_IDS:
        assert result[eid]["runtime_enabled"] is False
        assert result[eid]["contract_approved"] is False


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        validate_unique_ids(
            [{"id": "E11"}, {"id": "E11"}],
            "id",
        )


def test_missing_evidence_rejected(
    legacy_rules,
    extended_rows,
):
    with pytest.raises(ValueError):
        compile_evidence(legacy_rules, extended_rows[:-1])


def test_unknown_holder_rejected(
    legacy_rules,
    extended_rows,
):
    extended_rows[0]["holder_npc_id"] = "C99"

    with pytest.raises(ValueError):
        compile_evidence(legacy_rules, extended_rows)


def test_score_policy():
    assert set(PROPOSED_SCORES) == EXTENDED_IDS
    assert sum(PROPOSED_SCORES.values()) == 44


@pytest.mark.parametrize("eid", sorted(EXTENDED_IDS))
def test_all_evidence_have_routes(eid):
    policy = proposed_routes(eid, "CH02")

    assert policy.evidence_id == eid
    assert policy.routes

    for route in policy.routes:
        assert route.action_flag.startswith("ACT_")
        assert eid not in route.policy.required_evidence
        assert set(
            route.policy.required_evidence
        ).issubset(ALL_IDS)


@pytest.mark.parametrize(
    "eid",
    ["E12", "E14", "E19", "E22", "E23", "E25"],
)
def test_alternative_acquisition_routes(eid):
    assert len(proposed_routes(eid, "CH02").routes) == 2


def test_e30_requires_consent_and_safety():
    policy = proposed_routes("E30", "CH04")

    for route in policy.routes:
        assert "consent_and_safety_verified" in (
            route.policy.required_flags
        )

        assert set(route.policy.required_evidence) == {
            "E14",
            "E16",
            "E18",
        }
