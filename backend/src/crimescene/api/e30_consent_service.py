"""Issue #192 - explicit player consent for protected E30 content."""

from collections.abc import Callable

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)


REQUIRED_EVIDENCE = frozenset({"E14", "E16", "E18"})

ApprovalCheck = Callable[[GameState], bool]


class E30ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expectedRevision: int = Field(ge=0)
    consent: bool


def meets_e30_consent_prerequisites(state: GameState) -> bool:
    """Check server-owned progression state only."""

    if (
        state.case_id != "CASE-001"
        or state.content_version != "case001_1120"
        or state.phase != GamePhase.INVESTIGATION
        or state.outcome not in (None, "ONGOING")
        or state.current_chapter != "CH04"
        or "CH04" not in state.unlocked_chapters
    ):
        return False

    acquired = {
        eid
        for eid, evidence in state.evidence.items()
        if evidence.stage in {"found", "resolved"}
    }

    return (
        REQUIRED_EVIDENCE.issubset(acquired)
        and "E30" not in acquired
    )


def has_e30_approval(
    state: GameState,
    approval_check: ApprovalCheck | None,
) -> bool:
    """Fail closed unless a trusted server approval provider is wired."""

    if not meets_e30_consent_prerequisites(state):
        return False

    if not callable(approval_check):
        return False

    try:
        return approval_check(state) is True

    except Exception:
        # Approval failure must never grant access.
        return False


def e30_consent_available(
    state: GameState,
    approval_check: ApprovalCheck | None = None,
) -> bool:
    if state.e30_player_consent:
        return False

    return has_e30_approval(state, approval_check)


def grant_e30_player_consent(
    state: GameState,
    *,
    expected_revision: int,
    consent: bool,
    approval_check: ApprovalCheck | None = None,
) -> GameState:
    """Record player consent without granting evidence or story flags."""

    headers = {"Cache-Control": "private, no-store"}

    if consent is not True:
        raise HTTPException(
            422,
            "Explicit consent required",
            headers=headers,
        )

    if state.revision != expected_revision:
        raise HTTPException(
            409,
            "Game state changed",
            headers=headers,
        )

    if not has_e30_approval(state, approval_check):
        raise HTTPException(
            409,
            "Consent unavailable",
            headers=headers,
        )

    # Repeated requests with the current revision are idempotent.
    if state.e30_player_consent:
        return state

    return GameState.model_validate({
        **state.model_dump(mode="python"),
        "e30_player_consent": True,
        "revision": state.revision + 1,
    })
