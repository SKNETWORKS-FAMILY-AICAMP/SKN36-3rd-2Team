"""Issue #165 - evidence-driven NPC stage entry."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.expanded_dialogue import EVIDENCE_IDS


@dataclass(frozen=True, slots=True)
class PresentationStageRule:
    source_id: str
    source_sha256: str
    character_id: str
    target_stage: int
    evidence_ids: frozenset[str]

    def __post_init__(self):
        if not re.fullmatch(r"TRG-1120-\d{3}", self.source_id):
            raise ValueError("Invalid source ID")

        if not re.fullmatch(r"[a-f0-9]{64}", self.source_sha256):
            raise ValueError("Invalid source hash")

        if not re.fullmatch(r"C(?:0[1-9]|10)", self.character_id):
            raise ValueError("Invalid NPC")

        if self.target_stage not in (2, 3):
            raise ValueError("Invalid target stage")

        if (
            not isinstance(self.evidence_ids, frozenset)
            or not self.evidence_ids
            or not self.evidence_ids.issubset(EVIDENCE_IDS)
        ):
            raise ValueError("Invalid evidence requirements")

        if "E30" in self.evidence_ids:
            raise ValueError("E30 requires separate consent validation")


def compile_stage_candidates(
    index: list[dict],
) -> tuple[PresentationStageRule, ...]:
    """Interpret source stages without approving publication."""

    candidates = []

    for row in index:
        if row["stage"] not in (2, 3):
            continue

        if row["next_stage"] != row["stage"]:
            continue

        if row["trigger_type"] not in {
            "evidence", "evidence_combo"
        }:
            continue

        # Conditional acknowledgement and consent require
        # separate server-side contracts.
        if row["condition_key"] != "always":
            continue

        raw_ids = row["source_evidence_ids"].strip()

        if not re.fullmatch(
            r"E\d{2}(?:\+E\d{2})*",
            raw_ids,
        ):
            raise ValueError("Invalid source evidence expression")

        ids = raw_ids.split("+")

        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source evidence ID")

        if "E30" in ids:
            continue

        minimum = (
            2 if row["trigger_type"] == "evidence_combo"
            else 1
        )

        if len(ids) < minimum:
            raise ValueError("Incomplete presentation condition")

        candidates.append(
            PresentationStageRule(
                source_id=row["source_id"],
                source_sha256=row["source_sha256"],
                character_id=row["character_id"],
                target_stage=row["stage"],
                evidence_ids=frozenset(ids),
            )
        )

    return tuple(candidates)


def load_approved_stage_rules(
    index: list[dict],
    approvals: Mapping[str, str],
) -> tuple[PresentationStageRule, ...]:
    """Require explicit source ID and SHA-256 approval."""

    candidates = {
        rule.source_id: rule
        for rule in compile_stage_candidates(index)
    }

    approved = []

    for source_id, digest in approvals.items():
        rule = candidates.get(source_id)

        if rule is None or rule.source_sha256 != digest:
            raise ValueError("Invalid or stale stage approval")

        approved.append(rule)

    return tuple(approved)


def apply_presentation_stage(
    state: GameState,
    *,
    active_character_id: str,
    presented_evidence_id: str | None,
    rules: tuple[PresentationStageRule, ...],
) -> GameState:
    """Evaluate stage entry from verified presentation state."""

    if (
        state.case_id != "CASE-001"
        or state.content_version != "case001_1120"
        or state.phase != GamePhase.INVESTIGATION
        or state.outcome not in (None, "ONGOING")
        or active_character_id not in state.unlocked_characters
        or presented_evidence_id is None
    ):
        return state

    collected = {
        eid
        for eid, item in state.evidence.items()
        if item.stage in {"found", "resolved"}
    }

    presented = (
        set(state.presented.get(active_character_id, []))
        & collected
    )

    if presented_evidence_id not in presented:
        return state

    current = state.npc_stages.get(active_character_id, 1)
    target = current

    for rule in rules:
        if not isinstance(rule, PresentationStageRule):
            raise TypeError("Approved stage rule required")

        if (
            rule.character_id == active_character_id
            and presented_evidence_id in rule.evidence_ids
            and rule.evidence_ids.issubset(presented)
        ):
            target = max(target, rule.target_stage)

    if target == current:
        return state

    return GameState.model_validate({
        **state.model_dump(),
        "npc_stages": {
            **state.npc_stages,
            active_character_id: target,
        },
        "revision": state.revision + 1,
    })
