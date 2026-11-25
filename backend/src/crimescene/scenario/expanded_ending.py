"""Issue #165 - final reconstruction and versioned ending."""

import re
from collections.abc import Mapping
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.schemas.game_state import GamePhase, GameState

AXES = frozenset({
    "motive",
    "access",
    "timeline",
    "coverup",
})

FINAL_FLAG = "ACT_FINAL_RECONSTRUCTION_VERIFIED"

DEEP_EVIDENCE = frozenset({
    "E14", "E16", "E18", "E30",
})

DEEP_FLAGS = frozenset({
    "consent_and_safety_verified",
    "INF_2016_FORCED_DEPARTURE",
    "INF_RESPONSIBILITY_2016",
})


class ProofAxis(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )

    axis: Literal["motive", "access", "timeline", "coverup"]
    evidence_options: tuple[tuple[str, ...], ...]
    required_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_options(self):
        if not self.evidence_options:
            raise ValueError("Proof options required")

        for option in self.evidence_options:
            if (
                len(option) not in (2, 3)
                or len(option) != len(set(option))
                or any(
                    not re.fullmatch(
                        r"E(?:0[1-9]|[12][0-9])",
                        eid,
                    )
                    for eid in option
                )
            ):
                raise ValueError("Invalid proof evidence")

        for flag in self.required_flags:
            if not re.fullmatch(r"INF_[A-Z0-9_]+", flag):
                raise ValueError("Invalid inference requirement")

        return self


class ExpandedCaseTruth(CaseTruth):
    """Server-only truth and final reconstruction contract."""

    content_version: Literal["case001_1120"]
    proof_axes: tuple[ProofAxis, ...]

    @model_validator(mode="after")
    def validate_axes(self):
        if (
            len(self.proof_axes) != 4
            or {rule.axis for rule in self.proof_axes} != AXES
        ):
            raise ValueError("Four proof axes required")

        return self


def acquired_ids(state: GameState) -> frozenset[str]:
    return frozenset(
        eid
        for eid, item in state.evidence.items()
        if item.stage in {"found", "resolved"}
    )


def verify_reconstruction(
    state: GameState,
    *,
    selections: Mapping[str, list[str]],
    truth: ExpandedCaseTruth,
) -> GameState:
    """Verify at least three independent evidence axes."""

    if (
        state.case_id != "CASE-001"
        or state.content_version != "case001_1120"
        or state.phase != GamePhase.INVESTIGATION
        or state.outcome not in (None, "ONGOING")
        or state.current_chapter != "CH04"
        or not isinstance(truth, ExpandedCaseTruth)
        or truth.case_id != state.case_id
    ):
        raise PermissionError("Reconstruction unavailable")

    if not 3 <= len(selections) <= 4:
        raise ValueError("Three or four proof axes required")

    if not set(selections).issubset(AXES):
        raise ValueError("Unknown proof axis")

    acquired = acquired_ids(state)
    rules = {
        rule.axis: rule
        for rule in truth.proof_axes
    }

    verified = []

    for axis, evidence in selections.items():
        if (
            len(evidence) not in (2, 3)
            or len(evidence) != len(set(evidence))
        ):
            raise ValueError("Invalid evidence selection")

        ids = frozenset(evidence)

        if not ids.issubset(acquired):
            raise PermissionError("Evidence not collected")

        rule = rules[axis]

        if ids not in {
            frozenset(option)
            for option in rule.evidence_options
        }:
            return state

        if not set(rule.required_flags).issubset(state.flags):
            return state

        verified.append(ids)

    # At least three axes must use independent evidence sets.
    independent = any(
        not (a & b or b & c or a & c)
        for a, b, c in combinations(verified, 3)
    )

    if not independent or FINAL_FLAG in state.flags:
        return state

    return GameState.model_validate({
        **state.model_dump(),
        "flags": [*state.flags, FINAL_FLAG],
        "revision": state.revision + 1,
    })


def deep_requirements_met(state: GameState) -> bool:
    return (
        DEEP_EVIDENCE.issubset(acquired_ids(state))
        and DEEP_FLAGS.issubset(state.flags)
    )


def resolve_correct_ending(
    state: GameState,
) -> Literal["ESTIMATED", "FULL", "DEEP"]:
    """Classify a correct suspect selection."""

    if state.content_version != "case001_1120":
        raise ValueError("Invalid content version")

    if (
        "CH04" not in state.unlocked_chapters
        or FINAL_FLAG not in state.flags
    ):
        return "ESTIMATED"

    if deep_requirements_met(state):
        return "DEEP"

    return "FULL"
