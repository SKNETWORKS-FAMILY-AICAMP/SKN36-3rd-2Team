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

    recipients = authorized_recipients.get(evidence_id, frozenset())
    authorized = active_npc in recipients

    prompt = question.strip()

    if authorized:
        presentation_key = f"{active_npc}:{evidence_id}"

        # 제시한 증거와 연결된 후속 증거의 시나리오 질문을 사용합니다.
        # 실제 지식 공개 및 수집 여부는 기존 접근 정책이 검증합니다.
        for target_id, target_rule in sorted(rules.items()):
            if target_id == evidence_id:
                continue

            if getattr(target_rule, "holder", None) != active_npc:
                continue

            presentations = getattr(target_rule, "presentation", ())
            if (
                not isinstance(presentations, (list, tuple))
                or presentation_key not in presentations
            ):
                continue

            questions = getattr(target_rule, "q", ())
            if not isinstance(questions, (list, tuple)):
                continue

            related_question = next(
                (
                    item.strip()
                    for item in questions
                    if isinstance(item, str) and item.strip()
                ),
                None,
            )

            if related_question:
                prompt = f"{related_question} {prompt}"
                break

    prefix = f"제가 수집한 증거 '{title}'을 보여드리겠습니다. "

    if len(prefix) >= max_length:
        raise ValueError("증거 제목이 너무 깁니다.")

    return (
        (prefix + prompt)[:max_length],
        evidence_id if authorized else None,
    )