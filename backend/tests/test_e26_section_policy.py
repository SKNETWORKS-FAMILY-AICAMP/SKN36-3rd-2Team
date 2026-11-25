"""Security regression tests for E26 section access."""

import pytest

from crimescene.scenario.e26_section_policy import (
    allowed_e26_sections,
    can_access_e26_section,
)


EVIDENCE = frozenset({"E20", "E26"})
FLAGS = frozenset({"ACT_AUDIT_LOG_ACCESS_VERIFIED"})


def can_access(section="A", **overrides):
    context = {
        "acquired_evidence_ids": EVIDENCE,
        "verified_flags": FLAGS,
        "section_a_approved": True,
    }
    context.update(overrides)

    return can_access_e26_section(section, **context)


def test_section_a_allowed():
    assert can_access("A") is True


@pytest.mark.parametrize("section", ["B", "C"])
def test_restricted_sections_denied(section):
    assert can_access(section) is False


@pytest.mark.parametrize(
    "evidence",
    [
        frozenset(),
        frozenset({"E20"}),
        frozenset({"E26"}),
    ],
)
def test_missing_evidence_denied(evidence):
    assert can_access(
        acquired_evidence_ids=evidence
    ) is False


def test_missing_verified_flag_denied():
    assert can_access(
        verified_flags=frozenset()
    ) is False


def test_unrelated_flag_denied():
    assert can_access(
        verified_flags=frozenset({"UNRELATED"})
    ) is False


@pytest.mark.parametrize("approval", [False, None, 1, "true"])
def test_invalid_release_approval_denied(approval):
    assert can_access(
        section_a_approved=approval
    ) is False


def test_default_release_approval_denied():
    assert can_access_e26_section(
        "A",
        acquired_evidence_ids=EVIDENCE,
        verified_flags=FLAGS,
    ) is False


@pytest.mark.parametrize(
    "section",
    ["D", "", "a", "E26", "E26-A", None],
)
def test_unknown_section_denied(section):
    assert can_access(section) is False


@pytest.mark.parametrize(
    "section",
    ["B", "C"],
)
def test_unapproved_flags_cannot_grant_access(section):
    assert can_access(
        section,
        verified_flags=FLAGS | frozenset({
            "ADMIN",
            "E26_B_APPROVED",
            "E26_C_APPROVED",
        }),
    ) is False


def test_invalid_evidence_state_denied():
    assert can_access(
        acquired_evidence_ids=None
    ) is False


def test_invalid_flag_state_denied():
    assert can_access(
        verified_flags=None
    ) is False


def test_allowed_sections_contains_only_a():
    assert allowed_e26_sections(
        acquired_evidence_ids=EVIDENCE,
        verified_flags=FLAGS,
        section_a_approved=True,
    ) == frozenset({"A"})


def test_unapproved_release_returns_no_sections():
    assert allowed_e26_sections(
        acquired_evidence_ids=EVIDENCE,
        verified_flags=FLAGS,
    ) == frozenset()

# STEP 19-16-3-1: GameState integration

from crimescene.scenario.e26_section_policy import (
    can_acquire_e26_a,
    can_access_e26_section_for_state,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import GamePhase, GameState


def make_e26_state(**overrides):
    initial = create_initial_state("e26-policy-test")

    data = {
        **initial.model_dump(),
        "case_id": "CASE-001",
        "content_version": "case001_1120",
        "phase": GamePhase.INVESTIGATION,
        "current_chapter": "CH03",
        "unlocked_chapters": [
            "CH00", "CH01", "CH03",
        ],
        "evidence": {
            "E20": {"stage": "found"},
        },
        "flags": ["ACT_AUDIT_LOG_ACCESS_VERIFIED"],
        "outcome": None,
    }

    data.update(overrides)
    return GameState.model_validate(data)


def test_e26_acquisition_without_e26():
    state = make_e26_state()

    assert "E26" not in state.evidence

    assert can_acquire_e26_a(
        state,
        section_a_approved=True,
    ) is True


def test_e26_acquisition_requires_approval():
    assert can_acquire_e26_a(
        make_e26_state()
    ) is False


def test_e26_acquisition_requires_e20():
    state = make_e26_state(evidence={})

    assert can_acquire_e26_a(
        state,
        section_a_approved=True,
    ) is False


def test_e26_acquisition_requires_verified_flag():
    state = make_e26_state(flags=[])

    assert can_acquire_e26_a(
        state,
        section_a_approved=True,
    ) is False


def test_e26_acquisition_rejects_uncollected_e20():
    state = make_e26_state(
        evidence={"E20": {"stage": "locked"}},
    )

    assert can_acquire_e26_a(
        state,
        section_a_approved=True,
    ) is False


def test_e26_acquisition_rejects_other_case():
    state = make_e26_state(case_id="CASE-999")

    assert can_acquire_e26_a(
        state,
        section_a_approved=True,
    ) is False


def test_e26_acquisition_rejects_legacy_version():
    state = make_e26_state(
        content_version="case001_v7_1",
    )

    assert can_acquire_e26_a(
        state,
        section_a_approved=True,
    ) is False


def test_e26_acquisition_rejects_finished_game():
    state = make_e26_state(
        phase=GamePhase.FINISHED,
        outcome="SUCCESS",
    )

    assert can_acquire_e26_a(
        state,
        section_a_approved=True,
    ) is False


def test_e26_access_requires_collection():
    state = make_e26_state()

    assert can_access_e26_section_for_state(
        "A",
        state,
        section_a_approved=True,
    ) is False


@pytest.mark.parametrize("stage", ["found", "resolved"])
def test_e26_access_after_collection(stage):
    state = make_e26_state(
        evidence={
            "E20": {"stage": "found"},
            "E26": {"stage": stage},
        },
    )

    assert can_access_e26_section_for_state(
        "A",
        state,
        section_a_approved=True,
    ) is True


@pytest.mark.parametrize("section", ["B", "C"])
def test_e26_collection_does_not_unlock_restricted_sections(section):
    state = make_e26_state(
        evidence={
            "E20": {"stage": "found"},
            "E26": {"stage": "found"},
        },
        flags=[
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "E26_B_APPROVED",
            "E26_C_APPROVED",
        ],
        document_grants=["E26-B", "E26-C"],
    )

    assert can_access_e26_section_for_state(
        section,
        state,
        section_a_approved=True,
    ) is False


def test_e26_uncollected_stage_denied():
    state = make_e26_state(
        evidence={
            "E20": {"stage": "found"},
            "E26": {"stage": "locked"},
        },
    )

    assert can_access_e26_section_for_state(
        "A",
        state,
        section_a_approved=True,
    ) is False

from crimescene.api.expanded_acquisition_runtime import (
    validate_e26_release_contract,
)
from crimescene.scenario.content_compiler import proposed_routes


def make_e26_release_manifest():
    return {
        "approved_evidence": {
            "E20": {},
            "E26": {
                "score": 3,
                "required_evidence": ["E20"],
            },
        },
        "approved_e26_sections": ["A"],
        "approved_acquisition_routes": {
            "E26": proposed_routes(
                "E26", "CH03"
            ).model_dump(mode="json"),
        },
        "approved_investigation_actions": {
            "inspect-e26-a": {
                "evidence_id": "E26",
                "scene_id": "SC-0306",
                "chapter": "CH03",
                "route_ids": ["E26-A"],
                "character_id": None,
            },
        },
    }


def test_e26_release_accepts_section_a():
    assert validate_e26_release_contract(
        make_e26_release_manifest()
    ) is True


@pytest.mark.parametrize(
    "sections",
    [
        [],
        ["B"],
        ["C"],
        ["A", "B"],
        ["A", "C"],
        ["A", "B", "C"],
        ["A", "A"],
        "A",
        True,
        None,
    ],
)
def test_e26_release_rejects_invalid_sections(sections):
    manifest = make_e26_release_manifest()
    manifest["approved_e26_sections"] = sections

    with pytest.raises(PermissionError):
        validate_e26_release_contract(manifest)


def test_e26_release_requires_e20_approval():
    manifest = make_e26_release_manifest()
    del manifest["approved_evidence"]["E20"]

    with pytest.raises(PermissionError):
        validate_e26_release_contract(manifest)


def test_e26_release_rejects_wrong_score():
    manifest = make_e26_release_manifest()
    manifest["approved_evidence"]["E26"]["score"] = 6

    with pytest.raises(PermissionError):
        validate_e26_release_contract(manifest)


def test_e26_release_rejects_section_b_action():
    manifest = make_e26_release_manifest()

    manifest["approved_investigation_actions"][
        "inspect-e26-b"
    ] = {
        "evidence_id": "E26",
    }

    with pytest.raises(PermissionError):
        validate_e26_release_contract(manifest)


def test_e26_release_rejects_wrong_scene():
    manifest = make_e26_release_manifest()

    manifest["approved_investigation_actions"][
        "inspect-e26-a"
    ]["scene_id"] = "SC-0305"

    with pytest.raises(PermissionError):
        validate_e26_release_contract(manifest)


def test_release_without_e26_remains_compatible():
    assert validate_e26_release_contract({
        "approved_evidence": {"E20": {}},
    }) is False

# STEP 19-16-5: Graph access policy

from crimescene.scenario.e26_section_policy import (
    can_access_e26_holder_edge,
)


def make_e26_graph_state(**overrides):
    values = {
        "unlocked_characters": ["C01", "C02", "C10"],
        "evidence": {
            "E20": {"stage": "found"},
            "E26": {"stage": "found"},
        },
        "flags": ["ACT_AUDIT_LOG_ACCESS_VERIFIED"],
    }

    values.update(overrides)

    return make_e26_state(**values)


def graph_access(state=None, **overrides):
    values = {
        "edge_id": "HOLDER-1120-E26",
        "character_id": "C10",
        "section_a_approved": True,
        "graph_edge_approved": True,
    }

    values.update(overrides)

    return can_access_e26_holder_edge(
        make_e26_graph_state() if state is None else state,
        **values,
    )


def test_e26_graph_holder_allowed():
    assert graph_access() is True


@pytest.mark.parametrize(
    "character_id",
    ["C01", "C02", "C03", "C09", "", None],
)
def test_e26_graph_other_characters_denied(character_id):
    assert graph_access(
        character_id=character_id,
    ) is False


@pytest.mark.parametrize(
    "edge_id",
    [
        "E26",
        "E26-B",
        "E26-C",
        "HOLDER-1120-E30",
        "REL-E26-C01",
        "REL-E26-C02",
        "",
        None,
    ],
)
def test_e26_graph_unknown_edges_denied(edge_id):
    assert graph_access(edge_id=edge_id) is False


@pytest.mark.parametrize(
    "approval",
    [False, None, 1, "true"],
)
def test_e26_graph_requires_explicit_approval(approval):
    assert graph_access(
        graph_edge_approved=approval,
    ) is False


def test_e26_graph_requires_section_approval():
    assert graph_access(
        section_a_approved=False,
    ) is False


def test_e26_graph_requires_evidence():
    state = make_e26_graph_state(
        evidence={"E20": {"stage": "found"}},
    )

    assert graph_access(state) is False


def test_e26_graph_requires_verified_action():
    state = make_e26_graph_state(flags=[])

    assert graph_access(state) is False


def test_e26_graph_requires_unlocked_npc():
    state = make_e26_graph_state(
        unlocked_characters=["C01"],
    )

    assert graph_access(state) is False


def test_e26_graph_rejects_legacy_state():
    state = make_e26_graph_state(
        content_version="case001_v7_1",
    )

    assert graph_access(state) is False


def test_e26_graph_rejects_finished_game():
    state = make_e26_graph_state(
        phase=GamePhase.FINISHED,
        outcome="SUCCESS",
    )

    assert graph_access(state) is False

# STEP 19-16-5: Graph publication integration

from unittest.mock import MagicMock
from types import SimpleNamespace

from crimescene.retriever.expanded_graph_publication import (
    expected_e26_holder_contract,
    validate_e26_holder_approval,
    search_published_holders,
)
from crimescene.retriever.graph_context_builder import (
    build_graph_rag_context,
)
from crimescene.retriever.graph_evidence_search import (
    EvidenceGraphResult,
)
from crimescene.retriever.query_graph_retriever import (
    QuestionGraphContext,
)
from crimescene.scenario.schemas.evidence import EvidenceRule


def make_holder_manifest():
    return {
        "approved_evidence": {
            "E20": {},
            "E26": {},
        },
        "approved_e26_sections": ["A"],
        "approved_e26_holder_edge": (
            expected_e26_holder_contract()
        ),
    }


def make_holder_row():
    common = {
        "case_id": "CASE-001",
        "content_version": "case001_1120",
        "runtime_enabled": False,
    }

    return {
        "holder": {
            **common,
            "entity_id": "C10",
            "entity_type": "npc",
        },
        "evidence": {
            **common,
            "entity_id": "E26",
            "entity_type": "evidence",
        },
        "relation": {
            **common,
            **expected_e26_holder_contract(),
            "contract_approved": False,
        },
    }


def test_e26_holder_manifest_approved():
    assert validate_e26_holder_approval(
        make_holder_manifest()
    ) is True


def test_e26_holder_manifest_requires_independent_approval():
    manifest = make_holder_manifest()
    del manifest["approved_e26_holder_edge"]

    assert validate_e26_holder_approval(manifest) is False


@pytest.mark.parametrize(
    "field, value",
    [
        ("edge_id", "REL-E26-B"),
        ("source_id", "C01"),
        ("source_id", "C02"),
        ("target_id", "E30"),
        ("kind", "npc_relationship"),
        ("relation", "DELETE_REQUESTER"),
        ("source_sha256", "0" * 64),
    ],
)
def test_e26_holder_manifest_tampering_denied(field, value):
    manifest = make_holder_manifest()
    manifest["approved_e26_holder_edge"][field] = value

    with pytest.raises(PermissionError):
        validate_e26_holder_approval(manifest)


def test_e26_holder_manifest_requires_a_only():
    manifest = make_holder_manifest()
    manifest["approved_e26_sections"] = ["A", "B"]

    with pytest.raises(PermissionError):
        validate_e26_holder_approval(manifest)


def make_graph_driver(rows):
    driver = MagicMock()

    session = driver.session.return_value.__enter__.return_value
    session.run.return_value.data.return_value = rows

    return driver, session


def search_e26_graph(
    driver,
    *,
    state=None,
    character_id="C10",
    published=("E26",),
):
    return search_published_holders(
        driver=driver,
        state=(
            make_e26_graph_state()
            if state is None
            else state
        ),
        character_id=character_id,
        evidence_rules={
            "E26": SimpleNamespace(holder="C10"),
            "E30": SimpleNamespace(holder="C10"),
        },
        published_holder_ids=published,
    )


def test_e26_holder_search_approved():
    driver, session = make_graph_driver(
        [make_holder_row()]
    )

    results = search_e26_graph(driver)

    assert results == [
        EvidenceGraphResult(
            evidence_id="E26",
            holder_id="C10",
        )
    ]

    assert session.run.call_args.kwargs["edge_ids"] == [
        "HOLDER-1120-E26"
    ]


@pytest.mark.parametrize(
    "character_id",
    ["C01", "C02"],
)
def test_e26_holder_search_other_npc_denied(character_id):
    driver, _ = make_graph_driver([])

    assert search_e26_graph(
        driver,
        character_id=character_id,
    ) == []

    driver.session.assert_not_called()


def test_e26_holder_search_without_release_denied():
    driver, _ = make_graph_driver([])

    assert search_e26_graph(
        driver,
        published=(),
    ) == []

    driver.session.assert_not_called()


def test_e26_holder_search_without_flag_denied():
    driver, _ = make_graph_driver([])

    assert search_e26_graph(
        driver,
        state=make_e26_graph_state(flags=[]),
    ) == []

    driver.session.assert_not_called()


def test_e26_holder_search_without_collection_denied():
    driver, _ = make_graph_driver([])

    assert search_e26_graph(
        driver,
        state=make_e26_graph_state(
            evidence={"E20": {"stage": "found"}},
        ),
    ) == []

    driver.session.assert_not_called()


@pytest.mark.parametrize(
    "field, value",
    [
        ("source_id", "C01"),
        ("target_id", "E30"),
        ("relation", "ACCOUNT_OWNER"),
        ("kind", "npc_relationship"),
        ("source_sha256", "0" * 64),
        ("runtime_enabled", True),
        ("contract_approved", True),
    ],
)
def test_e26_holder_search_rejects_tampered_graph(field, value):
    row = make_holder_row()
    row["relation"][field] = value

    driver, _ = make_graph_driver([row])

    with pytest.raises(PermissionError):
        search_e26_graph(driver)


def test_e26_holder_search_missing_graph_row():
    driver, _ = make_graph_driver([])

    with pytest.raises(ValueError):
        search_e26_graph(driver)


def test_e26_holder_search_duplicate_graph_row():
    row = make_holder_row()

    driver, _ = make_graph_driver([row, row])

    with pytest.raises(ValueError):
        search_e26_graph(driver)


@pytest.mark.parametrize("approved", [False, True])
def test_e26_graph_context_requires_release_approval(approved):
    graph = QuestionGraphContext(
        character_id="C10",
        matched_entity_ids=("E26",),
        relations=(),
        evidence=(
            EvidenceGraphResult(
                evidence_id="E26",
                holder_id="C10",
            ),
        ),
    )

    result = build_graph_rag_context(
        graph,
        state=make_e26_graph_state(),
        registry=[],
        trusted_edges=[],
        evidence_rules={
            "E26": EvidenceRule(
                name="Audit log",
                score=3,
                holder="C10",
                prerequisites=[],
                presentation=[],
                q=[],
            ),
        },
        published_holder_ids=(
            ("E26",) if approved else ()
        ),
    )

    assert result.evidence_ids == (
        ("E26",) if approved else ()
    )

# STEP 19-16-6: Protected NPC presentation

from crimescene.trigger.evidence_presentation import (
    record_evidence_presentation,
)


@pytest.mark.parametrize("evidence_id", ["E26", "E30"])
def test_protected_npc_presentation_denied(evidence_id):
    state = make_e26_graph_state(
        evidence={
            "E20": {"stage": "found"},
            evidence_id: {"stage": "found"},
        },
    )

    before = state.model_dump(mode="json")

    with pytest.raises(
        PermissionError,
        match="Protected evidence presentation",
    ):
        record_evidence_presentation(
            state=state,
            active_character_id="C10",
            evidence_id=evidence_id,
            evidence_rules={
                evidence_id: EvidenceRule(
                    name="Protected evidence",
                    score=3,
                    holder="C10",
                    prerequisites=[],
                    presentation=[],
                    q=[],
                ),
            },
            allowed_recipients={
                evidence_id: frozenset({"C10"}),
            },
        )

    assert state.model_dump(mode="json") == before
