"""Issue #172 - deterministic and bounded NPC question recall."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from collections.abc import Sequence

from crimescene.chat.npc_dialogue_intent import (
    NPCDialogueIntent,
    classify_npc_dialogue_intent,
)
from crimescene.chat.npc_social_dialogue import (
    match_safe_social_intent,
)

if TYPE_CHECKING:
    from crimescene.chat.npc_session import NPCExchange


RECALL_OPENERS = {
    "C01": "네.",
    "C02": "네.",
    "C03": "아, 네.",
    "C04": "네.",
    "C05": "네, 말씀하셨죠.",
    "C06": "네.",
    "C07": "아, 그 질문이요!",
    "C08": "네.",
    "C09": "네, 그렇습니다.",
    "C10": "아, 네.",
}

SOCIAL_SUMMARIES = {
    "greeting": "제게 인사하셨습니다.",
    "talk": "이야기를 나눌 수 있는지 물으셨습니다.",
    "check_in": "제 안부를 물으셨습니다.",
    "thanks": "제게 감사 인사를 하셨습니다.",
    "farewell": "작별 인사를 하셨습니다.",
}

INTENT_SUMMARIES = {
    NPCDialogueIntent.IDENTITY:
        "제 소개를 요청하셨습니다.",
    NPCDialogueIntent.FOLLOW_UP:
        "직전 답변을 더 설명해 달라고 하셨습니다.",
    NPCDialogueIntent.RECALL:
        "이전 질문을 기억하는지 물으셨습니다.",
    NPCDialogueIntent.PRESSURE:
        "제 답변에 대해 추궁하셨습니다.",
}

RELATIONSHIP_PATTERN = re.compile(
    r"(?:신기범\s*씨를\s*어떻게\s*알고\s*계셨나요"
    r"|피해자와\s*어떤\s*관계였나요)"
)

NO_HISTORY_REPLY = (
    "아직 저와 나눈 대화가 없습니다."
)

UNKNOWN_QUESTION_REPLY = (
    "직전 질문의 구체적인 내용은 다시 말씀해 주세요."
)


def is_memory_recall_question(question: str) -> bool:
    """Only the existing bounded recall intent is eligible."""

    return (
        isinstance(question, str)
        and classify_npc_dialogue_intent(question)
        is NPCDialogueIntent.RECALL
    )


def build_memory_recall_reply(
    character_id: str,
    question: str,
    *,
    previous_question: str | None,
    previous_revision: int | None,
    current_revision: int,
) -> str | None:
    """Return only server-owned phrases.

    Historical user text is never copied into the reply.
    Historical NPC claims are never consumed.
    """

    if character_id not in RECALL_OPENERS:
        return None

    if not is_memory_recall_question(question):
        return None

    if type(current_revision) is not int or current_revision < 0:
        return None

    if previous_question is None:
        if previous_revision is not None:
            return None

        return NO_HISTORY_REPLY

    if (
        not isinstance(previous_question, str)
        or not previous_question.strip()
        or type(previous_revision) is not int
        or not 0 <= previous_revision <= current_revision
    ):
        return None

    previous = previous_question.strip()

    # Do not reflect arbitrary historical text.
    if (
        len(previous) > 400
        or any(c in previous for c in ("\r", "\n", "\x00"))
    ):
        return UNKNOWN_QUESTION_REPLY

    social = match_safe_social_intent(previous)

    if social is not None:
        summary = SOCIAL_SUMMARIES.get(social)

    else:
        normalized = previous.rstrip("?.!~… \t\r\n")

        if RELATIONSHIP_PATTERN.fullmatch(normalized):
            summary = "피해자와 어떤 관계였는지 물으셨습니다."

        else:
            intent = classify_npc_dialogue_intent(previous)
            summary = INTENT_SUMMARIES.get(intent)

    if summary is None:
        return UNKNOWN_QUESTION_REPLY

    return f"{RECALL_OPENERS[character_id]} {summary}"


def build_memory_recall_from_history(
    character_id: str,
    question: str,
    history: Sequence[NPCExchange],
    *,
    current_revision: int,
) -> str | None:
    """Use only the last exchange from the current NPC history."""

    previous = history[-1] if history else None

    return build_memory_recall_reply(
        character_id,
        question,
        previous_question=(
            previous.user_message if previous is not None else None
        ),
        previous_revision=(
            previous.state_revision if previous is not None else None
        ),
        current_revision=current_revision,
    )
