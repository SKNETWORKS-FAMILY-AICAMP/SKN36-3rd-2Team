
"""Issue #165 - reviewed NPC dialogue progression."""

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)

CONTENT_VERSION = "case001_1120"

EVIDENCE_IDS = frozenset(
    f"E{i:02d}" for i in range(1, 31)
)

TRIGGER_TYPES = frozenset({
    "question",
    "verbal_only",
    "evidence",
    "evidence_combo",
})

NPC_ACTION_FLAGS = {
    "C04": {"ACT_C04_SECURITY_QUESTION_VERIFIED"},
    "C05": {"ACT_C05_INTERVIEW_COMPLETED"},
    "C06": {"ACT_C06_ALIBI_INTERVIEW_COMPLETED"},
    "C07": {
        "ACT_C07_STATEMENT_VERIFIED",
        "ACT_C07_PACKAGE_STATEMENT_VERIFIED",
    },
    "C08": {"ACT_C08_STATEMENT_VERIFIED"},
    "C09": {"ACT_C09_VIDEO_ORIGINAL_VERIFIED"},
}


def compile_dialogue_index(rows: list[dict]) -> list[dict]:
    """Create stable source references without approving content."""

    if len(rows) != 166:
        raise ValueError("Expected 166 dialogue triggers")

    result = []

    for index, row in enumerate(rows, start=1):
        npc = row["npc_id"].strip()
        stage = int(row["stage"])
        trigger_type = row["trigger_type"]
        next_value = row["next_stage"].strip()

        if next_value == "\uc720\uc9c0":
            next_stage = stage
        else:
            next_stage = int(next_value)

        if not re.fullmatch(r"C(?:0[1-9]|10)", npc):
            raise ValueError("Invalid NPC ID")

        if stage not in (1, 2, 3):
            raise ValueError("Invalid current stage")

        if next_stage not in (1, 2, 3):
            raise ValueError("Invalid next stage")

        if trigger_type not in TRIGGER_TYPES:
            raise ValueError("Invalid trigger type")

        if row["output_mode"] not in {"fixed", "reference"}:
            raise ValueError("Invalid output mode")

        digest = hashlib.sha256(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        result.append({
            "source_id": f"TRG-1120-{index:03d}",
            "source_sha256": digest,
            "character_id": npc,
            "stage": stage,
            "next_stage": next_stage,
            "trigger_type": trigger_type,
            "condition_key": row["condition_key"],
            "source_evidence_ids": row["evidence_ids"],
            "output_mode": row["output_mode"],
            "output_order": row["output_order"],
            "contract_approved": False,
            "runtime_enabled": False,
        })

    return result


@dataclass(frozen=True, slots=True)
class ReviewedDialogueBinding:
    """Server-only binding of reviewed source and runtime rules."""

    source_id: str
    source_sha256: str
    trigger_id: str
    card_id: str
    character_id: str
    from_stage: int
    to_stage: int
    trigger_type: str
    required_evidence: tuple[str, ...] = ()
    required_presentations: tuple[str, ...] = ()
    action_flags: tuple[str, ...] = ()

    def __post_init__(self):
        if not re.fullmatch(
            r"TRG-1120-\d{3}", self.source_id
        ):
            raise ValueError("Invalid source ID")

        if not re.fullmatch(
            r"[a-f0-9]{64}", self.source_sha256
        ):
            raise ValueError("Invalid source hash")

        if not re.fullmatch(
            r"TRG-[A-Z0-9_-]+", self.trigger_id
        ):
            raise ValueError("Invalid runtime trigger ID")

        if not re.fullmatch(
            r"C(?:0[1-9]|10)", self.character_id
        ):
            raise ValueError("Invalid NPC")

        if not re.fullmatch(
            rf"K-{self.character_id}-(?:\d{{2}}|S\d{{2}})",
            self.card_id,
        ):
            raise ValueError("Card ownership mismatch")

        if (
            self.from_stage not in (1, 2, 3)
            or self.to_stage not in (1, 2, 3)
            or self.to_stage not in {
                self.from_stage,
                self.from_stage + 1,
            }
        ):
            raise ValueError("Invalid stage transition")

        if self.trigger_type not in TRIGGER_TYPES:
            raise ValueError("Invalid trigger type")

        for ids in (
            self.required_evidence,
            self.required_presentations,
        ):
            if not isinstance(ids, tuple):
                raise TypeError("Requirements must be tuples")

            if (
                len(ids) != len(set(ids))
                or not set(ids).issubset(EVIDENCE_IDS)
            ):
                raise ValueError("Invalid evidence requirements")

        minimum = {
            "evidence": 1,
            "evidence_combo": 2,
        }.get(self.trigger_type, 0)

        if len(self.required_presentations) < minimum:
            raise ValueError("Missing presentation requirements")

        if not isinstance(self.action_flags, tuple):
            raise TypeError("Action flags must be tuples")

        if not set(self.action_flags).issubset(
            NPC_ACTION_FLAGS.get(self.character_id, set())
        ):
            raise ValueError("Unauthorized NPC action flag")


def validate_source_binding(
    binding: ReviewedDialogueBinding,
    source: dict,
) -> None:
    """Reject stale or mismatched reviewed source bindings."""

    expected = (
        source["source_id"],
        source["source_sha256"],
        source["character_id"],
        source["stage"],
        source["next_stage"],
        source["trigger_type"],
    )

    actual = (
        binding.source_id,
        binding.source_sha256,
        binding.character_id,
        binding.from_stage,
        binding.to_stage,
        binding.trigger_type,
    )

    if expected != actual:
        raise ValueError("Reviewed source binding mismatch")


def apply_reviewed_dialogue(
    state: GameState,
    *,
    active_character_id: str,
    trigger_ids: Iterable[str],
    source_ids: Iterable[str],
    grounded: bool,
    presented_evidence_id: str | None,
    bindings: tuple[ReviewedDialogueBinding, ...],
) -> GameState:
    """Apply reviewed progression after verified dialogue."""

    if (
        state.case_id != "CASE-001"
        or state.content_version != CONTENT_VERSION
        or state.phase != GamePhase.INVESTIGATION
        or state.outcome not in (None, "ONGOING")
        or active_character_id not in state.unlocked_characters
        or grounded is not True
        or not bindings
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

    cited = set(source_ids) & set(state.disclosed_cards)
    matched = set(trigger_ids)

    current_stage = state.npc_stages.get(
        active_character_id, 1
    )

    next_stage = current_stage
    new_flags = set()
    seen = set()

    for binding in bindings:
        if not isinstance(binding, ReviewedDialogueBinding):
            raise TypeError("Reviewed binding required")

        if binding.source_id in seen:
            raise ValueError("Duplicate reviewed binding")

        seen.add(binding.source_id)

        if (
            binding.character_id != active_character_id
            or binding.from_stage != current_stage
            or binding.trigger_id not in matched
            or binding.card_id not in cited
        ):
            continue

        if not set(binding.required_evidence).issubset(
            collected
        ):
            continue

        if not set(
            binding.required_presentations
        ).issubset(presented):
            continue

        if binding.trigger_type in {
            "evidence",
            "evidence_combo",
        } and presented_evidence_id not in (
            binding.required_presentations
        ):
            continue

        next_stage = max(next_stage, binding.to_stage)
        new_flags.update(binding.action_flags)

    new_flags.difference_update(state.flags)

    if next_stage == current_stage and not new_flags:
        return state

    stages = dict(state.npc_stages)
    stages[active_character_id] = next_stage

    return GameState.model_validate({
        **state.model_dump(),
        "npc_stages": stages,
        "flags": [
            *state.flags,
            *sorted(new_flags),
        ],
        "revision": state.revision + 1,
    })
