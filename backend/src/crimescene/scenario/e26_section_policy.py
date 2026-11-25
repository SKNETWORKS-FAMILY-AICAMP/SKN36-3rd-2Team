"""Additional section-level access gate for E26."""

from typing import Final


E26_ID: Final = "E26"
REQUIRED_EVIDENCE: Final = frozenset({"E20", "E26"})
REQUIRED_FLAG: Final = "ACT_AUDIT_LOG_ACCESS_VERIFIED"
KNOWN_SECTIONS: Final = frozenset({"A", "B", "C"})


def can_access_e26_section(
    section: str,
    *,
    acquired_evidence_ids: frozenset[str],
    verified_flags: frozenset[str],
    section_a_approved: bool = False,
) -> bool:
    """Evaluate E26 access using trusted server-side state.

    This gate supplements the existing AccessPolicy and PolicyEvaluator.
    Release approval and player state must never come from request data.
    """

    if not isinstance(section, str):
        return False

    if section not in KNOWN_SECTIONS:
        return False

    # Sections B/C remain blocked until explicit contracts are approved.
    if section != "A":
        return False

    if section_a_approved is not True:
        return False

    if not isinstance(acquired_evidence_ids, frozenset):
        return False

    if not isinstance(verified_flags, frozenset):
        return False

    if not REQUIRED_EVIDENCE.issubset(acquired_evidence_ids):
        return False

    if REQUIRED_FLAG not in verified_flags:
        return False

    return True


def allowed_e26_sections(
    *,
    acquired_evidence_ids: frozenset[str],
    verified_flags: frozenset[str],
    section_a_approved: bool = False,
) -> frozenset[str]:
    """Return only explicitly authorized E26 sections."""

    return frozenset(
        section
        for section in KNOWN_SECTIONS
        if can_access_e26_section(
            section,
            acquired_evidence_ids=acquired_evidence_ids,
            verified_flags=verified_flags,
            section_a_approved=section_a_approved,
        )
    )

# STEP 19-16-3-1: GameState integration

from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.scenario.policy_evaluator import PolicyEvaluator


def _is_valid_e26_state(state: GameState) -> bool:
    return (
        isinstance(state, GameState)
        and state.case_id == "CASE-001"
        and state.content_version == "case001_1120"
    )


def _acquired_evidence_ids(state: GameState) -> frozenset[str]:
    return frozenset(
        eid
        for eid, item in state.evidence.items()
        if item.stage in PolicyEvaluator.VALID_EVIDENCE_STAGES
    )


def can_acquire_e26_a(
    state: GameState,
    *,
    section_a_approved: bool = False,
) -> bool:
    """Check acquisition eligibility before E26 is collected."""

    if not _is_valid_e26_state(state):
        return False

    if section_a_approved is not True:
        return False

    if state.phase != GamePhase.INVESTIGATION:
        return False

    if state.outcome not in (None, "ONGOING"):
        return False

    return (
        "E20" in _acquired_evidence_ids(state)
        and REQUIRED_FLAG in state.flags
    )


def can_access_e26_section_for_state(
    section: str,
    state: GameState,
    *,
    section_a_approved: bool = False,
) -> bool:
    """Check section access using trusted server-owned state."""

    if not _is_valid_e26_state(state):
        return False

    return can_access_e26_section(
        section,
        acquired_evidence_ids=_acquired_evidence_ids(state),
        verified_flags=frozenset(state.flags),
        section_a_approved=section_a_approved,
    )

# STEP 19-16-5: Graph access policy

E26_HOLDER_EDGE_ID: Final = "HOLDER-1120-E26"
E26_HOLDER_ID: Final = "C10"


def can_access_e26_holder_edge(
    state: GameState,
    *,
    edge_id: str,
    character_id: str,
    section_a_approved: bool = False,
    graph_edge_approved: bool = False,
) -> bool:
    """Allow only an explicitly approved E26 holder edge."""

    if graph_edge_approved is not True:
        return False

    if edge_id != E26_HOLDER_EDGE_ID:
        return False

    if character_id != E26_HOLDER_ID:
        return False

    if not _is_valid_e26_state(state):
        return False

    if state.phase != GamePhase.INVESTIGATION:
        return False

    if state.outcome not in (None, "ONGOING"):
        return False

    if character_id not in state.unlocked_characters:
        return False

    return can_access_e26_section_for_state(
        "A",
        state,
        section_a_approved=section_a_approved,
    )
