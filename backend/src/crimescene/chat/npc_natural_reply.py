"""Issue #25 - 검증된 NPC 진술의 안전한 화면 출력."""

import re
from types import MappingProxyType

from crimescene.chat.npc_emotional_state import (
    NPCEmotionalState,
    get_emotion_opener,
)
from crimescene.chat.npc_reaction import NPCReaction
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
)
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY

LEGACY_HEADER = "제가 확인한 자료에는 이렇게 나와 있어요."

QUOTE_PATTERN = re.compile(r"“(?P<quote>.+)” \(근거: (?P<source_id>[^)\r\n]+)\)")

# 사건 사실을 추가하지 않는 표현만 사용합니다.
NPC_OPENERS = {
    "C01": "",
    "C02": "",
    "C03": "",
    "C04": "",
    "C05": "",
    "C06": "제가 아는 바로는요.",
    "C07": "아, 그거요.",
    "C08": "",
    "C09": "",
    "C10": "그건요.",
}

REPEATED_OPENERS = {
    "C01": "다시 말씀드리겠습니다.",
    "C02": "같은 질문이군요.",
    "C03": "아까 말씀드린 부분인데요.",
    "C04": "다시 말씀드리죠.",
    "C05": "다시 설명드리겠습니다.",
    "C06": "다시 말씀드리자면요.",
    "C07": "아까도 물어보셨죠.",
    "C08": "같은 질문이네요.",
    "C09": "다시 말씀드리겠습니다.",
    "C10": "다시 말씀드리죠.",
}

NEW_EVIDENCE_OPENERS = {
    "C01": "그 부분은 말씀드리겠습니다.",
    "C02": "그 점에 대해서는 답하겠습니다.",
    "C03": "아, 그 부분은 설명드리겠습니다.",
    "C04": "말씀드리죠.",
    "C05": "확인할 수 있는 부분만 말씀드리겠습니다.",
    "C06": "그 부분은 차근차근 말씀드리겠습니다.",
    "C07": "아, 그 얘기라면 말씀드리죠.",
    "C08": "그 부분은 이야기하겠습니다.",
    "C09": "제가 아는 범위에서 말씀드리겠습니다.",
    "C10": "좋습니다. 그 부분은 말씀드리죠.",
}


# Style-only expressions; no new case facts or personal memories.
EXPANDED_NEUTRAL_OPENERS = MappingProxyType({
    "C01": "이 부분부터 말씀드리겠습니다.",
    "C02": "핵심만 말씀드리죠.",
    "C03": "그러니까, 이 부분입니다.",
    "C04": "이 부분입니다.",
    "C05": "내용을 구분해서 말씀드리겠습니다.",
    "C06": "차근차근 말씀드리자면요.",
    "C07": "아, 이 부분부터 말씀드릴게요.",
    "C08": "필요한 부분만 이야기하죠.",
    "C09": "이 부분을 말씀드리겠습니다.",
    "C10": "요점은 이렇습니다.",
})


def render_npc_speech(
    reply: NPCGroundedReply,
    *,
    context: AuthorizedMultisourceContext,
    reaction: NPCReaction,
    expanded_persona: bool = False,
    emotion: NPCEmotionalState | None = None,
) -> str:
    """승인된 인용문을 NPC의 화면용 대화로 변환합니다.

    원문을 재서술하지 않습니다.
    출처 ID는 reply.source_ids에 유지합니다.
    """

    if not isinstance(reply, NPCGroundedReply):
        raise TypeError("NPCGroundedReply가 필요합니다.")

    if not isinstance(context, AuthorizedMultisourceContext):
        raise TypeError("승인된 RAG 컨텍스트가 필요합니다.")

    if not isinstance(reaction, NPCReaction):
        raise TypeError("NPCReaction이 필요합니다.")

    if type(expanded_persona) is not bool:
        raise TypeError("Invalid expanded persona option")

    if reaction.character_id not in NPC_OPENERS:
        raise ValueError("지원하지 않는 NPC입니다.")

    emotional_opener = None

    if emotion is not None:
        if not isinstance(emotion, NPCEmotionalState):
            raise TypeError("Invalid emotional state")

        if (
            not expanded_persona
            or emotion.character_id != reaction.character_id
        ):
            raise ValueError("Invalid emotional context")

        emotional_opener = get_emotion_opener(emotion)

    if not reply.grounded:
        return FALLBACK_REPLY

    lines = reply.text.splitlines()

    # 검증된 기존 출력 형식만 변환합니다.
    if not 2 <= len(lines) <= 4:
        return FALLBACK_REPLY

    if lines[0] != LEGACY_HEADER:
        return FALLBACK_REPLY

    authorized: dict[str, list[str]] = {}

    for item in context.items:
        authorized.setdefault(item.source_id, []).append(item.content)

    verified_quotes: list[str] = []
    observed_source_ids: list[str] = []

    for line in lines[1:]:
        match = QUOTE_PATTERN.fullmatch(line)

        if match is None:
            return FALLBACK_REPLY

        quote = match.group("quote")
        source_id = match.group("source_id")

        if not 6 <= len(quote) <= 320:
            return FALLBACK_REPLY

        contents = authorized.get(source_id, [])

        # 현재 승인된 원문과 다시 비교합니다.
        if not any(quote in content for content in contents):
            return FALLBACK_REPLY

        verified_quotes.append(quote)

        if source_id not in observed_source_ids:
            observed_source_ids.append(source_id)

    # 응답에 포함된 출처와 실제 인용 출처가 일치해야 합니다.
    if tuple(observed_source_ids) != reply.source_ids:
        return FALLBACK_REPLY

    if reaction.mode == "new_evidence":
        opener = NEW_EVIDENCE_OPENERS[reaction.character_id]

    elif emotional_opener is not None:
        opener = emotional_opener

    elif reaction.mode == "repeated":
        opener = REPEATED_OPENERS[reaction.character_id]

    elif expanded_persona:
        opener = EXPANDED_NEUTRAL_OPENERS[reaction.character_id]

    else:
        opener = NPC_OPENERS[reaction.character_id]

    parts = []

    if opener:
        parts.append(opener)

    if expanded_persona:
        # Keep third-person source material recognizable as quotations.
        # Never turn it into the current NPC's personal experience.
        parts.extend(f"“{quote}”" for quote in verified_quotes)
    else:
        parts.extend(verified_quotes)

    return "\n".join(parts)
