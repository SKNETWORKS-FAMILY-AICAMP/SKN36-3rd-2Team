"""Evidence show vs. evidence-trigger distinction for CASE-001."""

from collections.abc import Mapping
from typing import Any


def resolve_evidence_reaction(
    question: str,
    evidence_id: str | None,
    *,
    active_npc: str,
    rules: Mapping[str, Any],
    authorized_recipients: Mapping[str, frozenset[str]],
    max_length: int = 4000,
) -> tuple[str, str | None]:
    """Supply a trusted evidence title and retain only authorized presentation effects.

    Any collected evidence may be *shown* to an unlocked NPC. For an unlisted
    evidence-NPC pair, only a normal, access-filtered RAG question is executed;
    no presentation flag is recorded and no hidden knowledge is unlocked.
    Ownership, acquisition and NPC unlock are checked by the API first.
    """
    if evidence_id is None:
        return question, None
    if not isinstance(question, str) or not question.strip():
        raise ValueError("질문이 비어 있습니다.")
    rule = rules.get(evidence_id)
    if rule is None:
        raise ValueError("등록되지 않은 증거입니다.")
    title = getattr(rule, "name", None)
    if not isinstance(title, str) or not title.strip():
        raise ValueError("증거 이름이 올바르지 않습니다.")
    if (
        isinstance(max_length, bool)
        or not isinstance(max_length, int)
        or max_length <= 0
    ):
        raise ValueError("질문 최대 길이가 잘못됐습니다.")

    # The evidence title comes from the trusted scenario catalog, not the client.
    prefix = f"제가 수집한 증거 '{title}'을 보여드리겠습니다. "
    if len(prefix) >= max_length:
        raise ValueError("증거 제목이 너무 깁니다.")
    prompted_question = (prefix + question.strip())[:max_length]

    permitted = authorized_recipients.get(evidence_id, frozenset())
    trigger_evidence_id = evidence_id if active_npc in permitted else None
    return prompted_question, trigger_evidence_id
