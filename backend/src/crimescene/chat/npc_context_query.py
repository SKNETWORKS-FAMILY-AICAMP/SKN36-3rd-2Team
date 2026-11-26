"""Issue #175 - authorized presentation-aware vector query."""

import re
from collections.abc import Mapping

from crimescene.chat.npc_evidence_dialogue import (
    EvidenceDialogueContext,
)
from crimescene.chat.npc_session import MAX_MESSAGE_LENGTH
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState


MAX_CONTEXT_SUFFIX = 200


def build_evidence_search_query(
    question: str,
    *,
    state: GameState,
    character_id: str,
    evidence_dialogue: EvidenceDialogueContext,
    evidence_rules: Mapping[str, EvidenceRule],
) -> str:
    """Expand retrieval input, never access permissions."""

    if not isinstance(question, str):
        raise TypeError("Question must be a string")

    question = question.strip()

    if not question or len(question) > MAX_MESSAGE_LENGTH:
        raise ValueError("Invalid question length")

    if not isinstance(
        evidence_dialogue, EvidenceDialogueContext
    ):
        raise TypeError("EvidenceDialogueContext required")

    evidence_dialogue.validate(state, character_id)

    eid = evidence_dialogue.evidence_id
    rule = evidence_rules.get(eid)

    if not isinstance(rule, EvidenceRule):
        raise PermissionError("Unknown evidence rule")

    title = rule.name.strip()

    if (
        not title
        or len(title) > MAX_CONTEXT_SUFFIX
        or any(c in title for c in "\r\n\x00")
    ):
        raise ValueError("Invalid evidence search title")

    parts = []

    if not re.search(
        rf"(?<![A-Za-z0-9]){re.escape(eid)}"
        r"(?![A-Za-z0-9])",
        question,
        flags=re.IGNORECASE,
    ):
        parts.append(eid)

    if title.casefold() not in question.casefold():
        parts.append(title)

    if not parts:
        return question

    suffix = " ".join(parts)

    expanded = f"{question} {suffix}"

    # Never truncate or replace the original question.
    if (
        len(suffix) > MAX_CONTEXT_SUFFIX
        or len(expanded) > MAX_MESSAGE_LENGTH
    ):
        return question

    return expanded
