"""Issue #173 - bounded, presentation-only NPC emotional state."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from crimescene.chat.npc_dialogue_intent import (
    NPCDialogueIntent,
    classify_npc_dialogue_intent,
)
from crimescene.chat.npc_social_dialogue import (
    match_safe_social_intent,
)
from crimescene.scenario.schemas.game_state import GameState


EMOTION_WINDOW = 8

# Pressure sensitivity, positive interaction sensitivity.
NPC_SENSITIVITY = MappingProxyType({
    "C01": (2, 1),
    "C02": (3, 1),
    "C03": (2, 2),
    "C04": (3, 1),
    "C05": (1, 3),
    "C06": (1, 3),
    "C07": (2, 3),
    "C08": (3, 1),
    "C09": (1, 2),
    "C10": (2, 2),
})


class NPCMood(StrEnum):
    NEUTRAL = "NEUTRAL"
    COOPERATIVE = "COOPERATIVE"
    RELAXED = "RELAXED"
    GUARDED = "GUARDED"
    TENSE = "TENSE"


@dataclass(frozen=True, slots=True)
class NPCEmotionalState:
    character_id: str
    trust: int = 50
    stress: int = 20
    guard: int = 20

    def __post_init__(self):
        if self.character_id not in NPC_SENSITIVITY:
            raise ValueError("Unknown NPC")

        for value in (self.trust, self.stress, self.guard):
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("Invalid emotion score")

    @property
    def mood(self) -> NPCMood:
        if self.stress >= 70:
            return NPCMood.TENSE

        if self.guard >= 45:
            return NPCMood.GUARDED

        if self.trust >= 75 and self.stress <= 25:
            return NPCMood.RELAXED

        if self.trust >= 60:
            return NPCMood.COOPERATIVE

        return NPCMood.NEUTRAL


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def derive_npc_emotional_state(
    query: str,
    *,
    state: GameState,
    character_id: str,
    history: Sequence = (),
    evidence_just_presented: bool = False,
) -> NPCEmotionalState:
    """Calculate mood from server-scoped history without state mutation."""

    from crimescene.chat.npc_session import (
        NPCExchange,
        MAX_MESSAGE_LENGTH,
    )

    if not isinstance(state, GameState):
        raise TypeError("GameState required")

    if (
        state.case_id != "CASE-001"
        or state.content_version != "case001_1120"
    ):
        raise ValueError("Unsupported content version")

    if not isinstance(character_id, str):
        raise TypeError("Invalid character ID")

    if character_id not in NPC_SENSITIVITY:
        raise ValueError("Unknown NPC")

    if character_id not in state.unlocked_characters:
        raise PermissionError("Character unavailable")

    if type(state.revision) is not int or state.revision < 0:
        raise ValueError("Invalid current revision")

    if type(evidence_just_presented) is not bool:
        raise TypeError("Invalid evidence presentation")

    if not isinstance(query, str):
        raise TypeError("Invalid query")

    if not query.strip() or len(query) > MAX_MESSAGE_LENGTH:
        raise ValueError("Invalid query length")

    if not isinstance(history, (tuple, list)):
        raise TypeError("Invalid conversation history")

    pressure, positive = NPC_SENSITIVITY[character_id]

    trust, stress, guard = 50, 20, 20

    # Each social intent contributes at most once per window.
    used_social_intents = set()

    questions = []

    for exchange in history[-(EMOTION_WINDOW - 1):]:
        if not isinstance(exchange, NPCExchange):
            raise TypeError("Invalid conversation exchange")

        if (
            type(exchange.state_revision) is not int
            or not 0 <= exchange.state_revision <= state.revision
        ):
            continue

        previous = exchange.user_message

        if (
            not isinstance(previous, str)
            or not previous.strip()
            or len(previous) > MAX_MESSAGE_LENGTH
        ):
            continue

        questions.append(previous)

    # Evidence turns retain their existing dedicated reaction path.
    if not evidence_just_presented:
        questions.append(query)

    for question in questions:
        social = match_safe_social_intent(question)

        if social is not None:
            if social in used_social_intents:
                continue

            used_social_intents.add(social)

            trust = _clamp(trust + 3 + positive)
            stress = _clamp(stress - 3)
            guard = _clamp(guard - 3)

            continue

        intent = classify_npc_dialogue_intent(question)

        if intent is NPCDialogueIntent.PRESSURE:
            trust = _clamp(trust - 4 - pressure)
            stress = _clamp(stress + 10 + 4 * pressure)
            guard = _clamp(guard + 18 + 4 * pressure)

    return NPCEmotionalState(
        character_id=character_id,
        trust=trust,
        stress=stress,
        guard=guard,
    )


MOOD_GUIDANCE = MappingProxyType({
    NPCMood.NEUTRAL:
        "기본적인 대화 태도를 유지한다.",
    NPCMood.COOPERATIVE:
        "협조적인 태도로 승인된 근거의 핵심을 선택한다.",
    NPCMood.RELAXED:
        "차분하고 부담 없는 표현을 유지한다.",
    NPCMood.GUARDED:
        "신중하고 절제된 태도를 유지한다.",
    NPCMood.TENSE:
        "짧고 통제된 표현을 유지한다.",
})


def build_npc_emotion_prompt(
    emotion: NPCEmotionalState,
) -> str:

    if not isinstance(emotion, NPCEmotionalState):
        raise TypeError("Invalid emotional state")

    return "\n".join((
        "[NPC EMOTIONAL STATE]",
        MOOD_GUIDANCE[emotion.mood],
        "감정 상태는 서버가 계산한 표현 지침이다.",
        "감정 상태를 사건 사실이나 유죄의 근거로 사용하지 않는다.",
        "신뢰도와 긴장도는 정보 공개 권한을 변경하지 않는다.",
        "감정이나 숨겨진 동기, 기억, 자백을 새로 생성하지 않는다.",
        "현재 승인된 원문과 기존 JSON 규칙만 사용한다.",
    ))


# Order: cooperative, relaxed, guarded, tense.
EMOTION_OPENERS = MappingProxyType({
    "C01": (
        "차근차근 말씀드리겠습니다.",
        "편하게 이야기하겠습니다.",
        "확인된 부분만 말씀드리겠습니다.",
        "잠시만요. 핵심만 말씀드리겠습니다.",
    ),
    "C02": (
        "필요한 내용을 설명하죠.",
        "차분히 이야기하죠.",
        "확인 가능한 내용만 이야기하겠습니다.",
        "질문의 핵심만 답하죠.",
    ),
    "C03": (
        "네, 설명해 드릴게요.",
        "아, 천천히 말씀드릴게요.",
        "아, 이 부분만 말씀드리겠습니다.",
        "잠깐만요. 이 부분만 설명하죠.",
    ),
    "C04": (
        "네. 정리해서 말씀드리죠.",
        "차분히 설명하겠습니다.",
        "확인된 내용만 답하겠습니다.",
        "핵심만 답하겠습니다.",
    ),
    "C05": (
        "네. 차근차근 설명해 드리겠습니다.",
        "편하게 들으셔도 됩니다.",
        "내용을 구분해서 확인하겠습니다.",
        "잠시만요. 내용을 정리하겠습니다.",
    ),
    "C06": (
        "천천히 설명해 드리겠습니다.",
        "차분하게 이야기하겠습니다.",
        "확인할 수 있는 범위에서 답하겠습니다.",
        "잠시 정리해서 말씀드리겠습니다.",
    ),
    "C07": (
        "네! 설명해 드릴게요.",
        "편하게 들어 주세요.",
        "아, 확인된 내용부터 이야기할게요.",
        "잠깐만요. 이 부분부터 이야기하죠.",
    ),
    "C08": (
        "네. 정리해서 이야기하죠.",
        "차분하게 말씀드리죠.",
        "확실한 부분만 이야기하겠습니다.",
        "필요한 내용만 답하죠.",
    ),
    "C09": (
        "네, 설명드리겠습니다.",
        "천천히 이야기하겠습니다.",
        "확인 가능한 범위에서 답하겠습니다.",
        "잠시만요. 내용을 정리하죠.",
    ),
    "C10": (
        "좋습니다. 설명하죠.",
        "편하게 말씀드리겠습니다.",
        "확인된 부분부터 이야기하죠.",
        "요점만 말씀드리죠.",
    ),
})

MOOD_INDEX = MappingProxyType({
    NPCMood.COOPERATIVE: 0,
    NPCMood.RELAXED: 1,
    NPCMood.GUARDED: 2,
    NPCMood.TENSE: 3,
})


def get_emotion_opener(
    emotion: NPCEmotionalState,
) -> str | None:

    if not isinstance(emotion, NPCEmotionalState):
        raise TypeError("Invalid emotional state")

    index = MOOD_INDEX.get(emotion.mood)

    if index is None:
        return None

    return EMOTION_OPENERS[emotion.character_id][index]
