"""Issue #175 - bounded, fact-free pressure clarification."""

import re
from types import MappingProxyType

from crimescene.chat.npc_emotional_state import (
    NPCEmotionalState,
    NPCMood,
)
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)


MAX_PRESSURE_LENGTH = 120

PRESSURE_PATTERN = re.compile(
    r"(?:"
    r"(?:혹시\s*)?(?:저한테\s*)?"
    r"숨기고\s*있는\s*게\s*있으세요"
    r"|거짓말하거나\s*숨기고\s*있는\s*내용이\s*있습니까"
    r"|거짓말하고\s*있는\s*거\s*아니에요"
    r"|혹시\s*거짓말하고\s*계세요"
    r"|뭔가\s*숨기고\s*있죠"
    r"|숨기는\s*게\s*있나요"
    r")[.!?~]*"
)

PRESSURE_REPLIES = MappingProxyType({
    "C01": "어떤 부분을 의심하시는 겁니까?",
    "C02": "구체적으로 질문하시죠.",
    "C03": "아, 어떤 부분이 이상하다는 건가요?",
    "C04": "의심되는 부분을 정확히 말씀하세요.",
    "C05": "어떤 점이 마음에 걸리시는 건가요?",
    "C06": "어떤 부분인지 먼저 말씀해 주세요.",
    "C07": "잠깐, 어떤 이야기부터 확인할까요?",
    "C08": "무엇을 확인하려는 건지 말씀하시죠.",
    "C09": "구체적인 질문을 부탁드립니다.",
    "C10": "어느 부분을 말씀하시는 거죠?",
})

MOOD_PREFIXES = MappingProxyType({
    NPCMood.NEUTRAL: "",
    NPCMood.COOPERATIVE: "네. ",
    NPCMood.RELAXED: "좋습니다. ",
    NPCMood.GUARDED: "잠시만요. ",
    NPCMood.TENSE: "질문을 하나씩 하시죠. ",
})


def is_generic_pressure_question(question):
    if not isinstance(question, str):
        return False

    normalized = question.strip()

    if not 1 <= len(normalized) <= MAX_PRESSURE_LENGTH:
        return False

    if any(c in normalized for c in "\r\n\x00"):
        return False

    return PRESSURE_PATTERN.fullmatch(normalized) is not None


def pressure_dialogue_enabled(state):
    return (
        isinstance(state, GameState)
        and state.case_id == "CASE-001"
        and state.content_version == "case001_1120"
        and state.phase == GamePhase.INVESTIGATION
        and state.outcome in (None, "ONGOING")
    )


def build_pressure_reply(
    question,
    *,
    state,
    character_id,
    emotion,
):
    if (
        not pressure_dialogue_enabled(state)
        or not is_generic_pressure_question(question)
        or character_id not in PRESSURE_REPLIES
        or character_id not in state.unlocked_characters
    ):
        raise PermissionError("Pressure clarification unavailable")

    if not isinstance(emotion, NPCEmotionalState):
        raise TypeError("NPCEmotionalState required")

    if emotion.character_id != character_id:
        raise PermissionError("Emotion character mismatch")

    return (
        MOOD_PREFIXES[emotion.mood]
        + PRESSURE_REPLIES[character_id]
    )


def is_approved_pressure_reply(
    character_id,
    question,
    answer,
    *,
    state,
):
    """Allow only server-owned, fact-free response variants."""

    if (
        not pressure_dialogue_enabled(state)
        or character_id not in PRESSURE_REPLIES
        or character_id not in state.unlocked_characters
        or not is_generic_pressure_question(question)
        or not isinstance(answer, str)
    ):
        return False

    return answer in {
        prefix + PRESSURE_REPLIES[character_id]
        for prefix in MOOD_PREFIXES.values()
    }
