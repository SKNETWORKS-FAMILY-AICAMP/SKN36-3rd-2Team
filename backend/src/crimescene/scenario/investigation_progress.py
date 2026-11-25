"""Issue #165 - objective and evidence inference engine."""

import re
from dataclasses import dataclass

from crimescene.scenario.e26_section_policy import (
    can_access_e26_section_for_state,
)

from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)

EVIDENCE_IDS = frozenset(
    f"E{i:02d}" for i in range(1, 31)
)

CHAPTERS = frozenset(
    f"CH{i:02d}" for i in range(5)
)

PROTECTED_INFERENCES = frozenset({
    "INF_DEEP_GATE",
    "INF_2016_TESTIMONY",
})


def collected_evidence(state: GameState) -> frozenset[str]:
    return frozenset(
        eid
        for eid, item in state.evidence.items()
        if item.stage in {"found", "resolved"}
    )


def validate_evidence_ids(ids):
    if (
        not isinstance(ids, frozenset)
        or not ids.issubset(EVIDENCE_IDS)
    ):
        raise ValueError("Invalid evidence requirements")


@dataclass(frozen=True, slots=True)
class ObjectiveRule:
    objective_id: str
    chapter: str
    required_evidence: frozenset[str]
    target_evidence: frozenset[str]
    completion_flags: frozenset[str] = frozenset()

    def __post_init__(self):
        if not re.fullmatch(
            r"OBJ_[A-Z0-9_]+", self.objective_id
        ):
            raise ValueError("Invalid objective ID")

        if self.chapter not in CHAPTERS:
            raise ValueError("Invalid chapter")

        validate_evidence_ids(self.required_evidence)
        validate_evidence_ids(self.target_evidence)

        if not self.target_evidence and not self.completion_flags:
            raise ValueError("Completion condition required")

        if (
            "E30" in self.target_evidence
            or "E30" in self.required_evidence
        ):
            raise ValueError("Protected objective requires separate gate")


@dataclass(frozen=True, slots=True)
class InferenceRule:
    rule_id: str
    inference_id: str
    chapter: str
    evidence_ids: frozenset[str]
    required_flags: frozenset[str] = frozenset()

    def __post_init__(self):
        if not re.fullmatch(
            r"LINK-\d{3}", self.rule_id
        ):
            raise ValueError("Invalid link ID")

        if not re.fullmatch(
            r"INF_[A-Z0-9_]+", self.inference_id
        ):
            raise ValueError("Invalid inference ID")

        if self.chapter not in CHAPTERS:
            raise ValueError("Invalid chapter")

        validate_evidence_ids(self.evidence_ids)

        if len(self.evidence_ids) not in (2, 3):
            raise ValueError("Two or three evidence items required")

        if (
            "E30" in self.evidence_ids
            or self.inference_id in PROTECTED_INFERENCES
        ):
            raise ValueError("Protected inference")

        # E26 is authorized only for the exact section-A inference.
        if (
            "E26" in self.evidence_ids
            or self.inference_id == "INF_POST_EVENT_DELETE"
        ):
            if (
                self.inference_id != "INF_POST_EVENT_DELETE"
                or self.chapter != "CH03"
                or self.evidence_ids != frozenset({"E20", "E26"})
                or self.required_flags != frozenset({
                    "ACT_AUDIT_LOG_ACCESS_VERIFIED"
                })
            ):
                raise ValueError("Invalid E26 inference contract")


def objective_status(
    state: GameState,
    rule: ObjectiveRule,
) -> str:
    """Compute status without mutating player state."""

    if state.content_version != "case001_1120":
        return "LOCKED"

    if state.case_id != "CASE-001":
        return "LOCKED"

    acquired = collected_evidence(state)

    if (
        rule.chapter not in state.unlocked_chapters
        or not rule.required_evidence.issubset(acquired)
    ):
        return "LOCKED"

    if (
        rule.target_evidence.issubset(acquired)
        and rule.completion_flags.issubset(state.flags)
    ):
        return "COMPLETED"

    return "ACTIVE"


@dataclass(frozen=True, slots=True)
class InferenceResult:
    state: GameState
    accepted: bool
    inference_ids: tuple[str, ...]
    created: bool


def submit_inference(
    state: GameState,
    *,
    evidence_ids: frozenset[str],
    rules: tuple[InferenceRule, ...],
    e26_section_a_approved: bool = False,
) -> InferenceResult:
    """Validate a player-selected evidence combination."""

    validate_evidence_ids(evidence_ids)

    if len(evidence_ids) not in (2, 3):
        raise ValueError("Invalid evidence combination")

    if (
        state.case_id != "CASE-001"
        or state.content_version != "case001_1120"
        or state.phase != GamePhase.INVESTIGATION
        or state.outcome not in (None, "ONGOING")
    ):
        raise PermissionError("Inference unavailable")

    if not evidence_ids.issubset(collected_evidence(state)):
        raise PermissionError("Evidence not collected")

    if "E30" in evidence_ids:
        raise PermissionError("Protected evidence")

    if "E26" in evidence_ids:
        if (
            evidence_ids != frozenset({"E20", "E26"})
            or not can_access_e26_section_for_state(
                "A",
                state,
                section_a_approved=e26_section_a_approved,
            )
        ):
            raise PermissionError("E26 inference denied")

    matched = set()
    seen = set()

    for rule in rules:
        if not isinstance(rule, InferenceRule):
            raise TypeError("Invalid inference rule")

        if rule.rule_id in seen:
            raise ValueError("Duplicate inference rule")

        seen.add(rule.rule_id)

        if (
            rule.chapter == state.current_chapter
            and rule.chapter in state.unlocked_chapters
            and rule.evidence_ids == evidence_ids
            and rule.required_flags.issubset(state.flags)
        ):
            matched.add(rule.inference_id)

    if not matched:
        return InferenceResult(
            state=state,
            accepted=False,
            inference_ids=(),
            created=False,
        )

    new_flags = matched.difference(state.flags)

    if not new_flags:
        return InferenceResult(
            state=state,
            accepted=True,
            inference_ids=tuple(sorted(matched)),
            created=False,
        )

    updated = GameState.model_validate({
        **state.model_dump(),
        "flags": [
            *state.flags,
            *sorted(new_flags),
        ],
        "revision": state.revision + 1,
    })

    return InferenceResult(
        state=updated,
        accepted=True,
        inference_ids=tuple(sorted(matched)),
        created=True,
    )
