"""Issue #174 - presentation-only evidence dialogue context."""

import re
from dataclasses import dataclass
from types import MappingProxyType

from crimescene.chat.npc_emotional_state import (
    EMOTION_OPENERS,
    NPCEmotionalState,
    NPCMood,
    get_emotion_opener,
)
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
)
from crimescene.scenario.schemas.game_state import GameState


NPC_IDS = frozenset(f"C{i:02d}" for i in range(1, 11))
EVIDENCE_ID_PATTERN = re.compile(r"E(?:0[1-9]|[12][0-9]|30)")
PROTECTED_EVIDENCE = frozenset({"E26", "E30"})


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceDialogueContext:
    """Server-owned presentation metadata, never an access grant."""

    session_id: str
    character_id: str
    evidence_id: str
    revision: int
    first_presentation: bool

    def validate(
        self,
        state: GameState,
        character_id: str,
    ) -> None:

        if not isinstance(state, GameState):
            raise TypeError("GameState required")

        if (
            state.case_id != "CASE-001"
            or state.content_version != "case001_1120"
        ):
            raise PermissionError("Unsupported evidence context")

        if (
            not isinstance(self.character_id, str)
            or self.character_id not in NPC_IDS
            or self.character_id != character_id
            or character_id not in state.unlocked_characters
        ):
            raise PermissionError("Invalid evidence character")

        if (
            not isinstance(self.session_id, str)
            or self.session_id != state.session_id
        ):
            raise PermissionError("Evidence session mismatch")

        if (
            type(self.revision) is not int
            or self.revision < 0
            or self.revision != state.revision
        ):
            raise PermissionError("Evidence revision mismatch")

        if type(self.first_presentation) is not bool:
            raise TypeError("Invalid presentation status")

        if (
            not isinstance(self.evidence_id, str)
            or EVIDENCE_ID_PATTERN.fullmatch(self.evidence_id) is None
            or self.evidence_id in PROTECTED_EVIDENCE
        ):
            raise PermissionError("Evidence unavailable")

        if state.outcome not in (None, "ONGOING"):
            raise PermissionError("Game unavailable")

        evidence = state.evidence.get(self.evidence_id)

        if evidence is None or evidence.stage not in {
            "found", "resolved"
        }:
            raise PermissionError("Evidence not collected")

        if self.evidence_id not in state.presented.get(
            character_id, []
        ):
            raise PermissionError("Evidence not presented")


def build_evidence_dialogue_context(
    *,
    before: GameState,
    after: GameState,
    character_id: str,
    evidence_id: str,
    presentation_created: bool,
) -> EvidenceDialogueContext:
    """Build only after the existing presentation service succeeds."""

    if not isinstance(before, GameState):
        raise TypeError("Previous GameState required")

    if not isinstance(after, GameState):
        raise TypeError("Updated GameState required")

    if type(presentation_created) is not bool:
        raise TypeError("Invalid presentation status")

    if (
        before.session_id != after.session_id
        or before.case_id != after.case_id
        or before.content_version != after.content_version
        or after.revision < before.revision
    ):
        raise PermissionError("Invalid presentation transition")

    context = EvidenceDialogueContext(
        session_id=after.session_id,
        character_id=character_id,
        evidence_id=evidence_id,
        revision=after.revision,
        first_presentation=presentation_created,
    )

    context.validate(after, character_id)

    previously_presented = evidence_id in before.presented.get(
        character_id, []
    )

    if presentation_created != (not previously_presented):
        raise PermissionError("Presentation status mismatch")

    if presentation_created and after.revision <= before.revision:
        raise PermissionError("Invalid presentation revision")

    previous_evidence = before.evidence.get(evidence_id)

    if (
        previous_evidence is None
        or previous_evidence.stage not in {"found", "resolved"}
        or character_id not in before.unlocked_characters
    ):
        raise PermissionError("Invalid previous evidence state")

    return context


def build_evidence_dialogue_prompt(
    evidence: EvidenceDialogueContext,
    context: AuthorizedMultisourceContext,
) -> str:

    if not isinstance(evidence, EvidenceDialogueContext):
        raise TypeError("EvidenceDialogueContext required")

    if not isinstance(context, AuthorizedMultisourceContext):
        raise TypeError("AuthorizedMultisourceContext required")

    status = (
        "최초 제시"
        if evidence.first_presentation
        else "동일 증거 재제시"
    )

    direct_evidence_available = any(
        item.kind == "evidence"
        and item.item_id == evidence.evidence_id
        and item.source_id == evidence.evidence_id
        for item in context.items
    )

    guidance = (
        "현재 승인 근거에 제시된 증거의 직접 근거가 있다. "
        "질문과 관련된 경우 해당 근거를 우선 검토한다."
        if direct_evidence_available
        else
        "현재 승인 근거에서 직접 증거 항목이 확인되지 않았다. "
        "증거와 다른 진술의 관계를 임의로 추론하지 않는다."
    )

    return "\n".join((
        "[NPC EVIDENCE DIALOGUE]",
        f"제시 상황: {status}",
        guidance,
        "이전 진술은 현재 승인 원문으로 재검증된 기록만 참고한다.",
        "증거 제시만으로 자백, 거짓말, 모순 또는 유죄를 추정하지 않는다.",
        "증거 제시 이력은 새로운 정보 공개 권한이 아니다.",
        "질문에 직접 관련된 현재 승인 원문만 인용한다.",
        "관련 근거가 없다면 기존 빈 quotes 배열을 반환한다.",
    ))


REPEATED_EVIDENCE_OPENERS = MappingProxyType({
    "C01": "앞서 보여주신 자료군요. 다시 확인하겠습니다.",
    "C02": "이미 제시하신 자료군요. 확인하죠.",
    "C03": "아, 앞서 보여주신 자료네요.",
    "C04": "다시 보여주시는군요.",
    "C05": "앞서 제시하신 자료를 다시 확인하겠습니다.",
    "C06": "전에 보여주셨던 자료군요.",
    "C07": "아, 아까 그 자료군요.",
    "C08": "앞서 보여주셨던 자료네요.",
    "C09": "이전에 제시하신 자료군요.",
    "C10": "다시 그 자료군요. 확인하죠.",
})

FIRST_PREFIX = "제시하신 자료군요."
REPEAT_PREFIX = "앞서 제시하신 자료군요."


def get_evidence_dialogue_opener(
    evidence: EvidenceDialogueContext,
    emotion: NPCEmotionalState | None = None,
) -> str | None:

    if not isinstance(evidence, EvidenceDialogueContext):
        raise TypeError("Invalid evidence context")

    if evidence.character_id not in NPC_IDS:
        raise ValueError("Unknown NPC")

    if emotion is not None:
        if not isinstance(emotion, NPCEmotionalState):
            raise TypeError("Invalid emotional state")

        if emotion.character_id != evidence.character_id:
            raise ValueError("Emotional context mismatch")

        if emotion.mood in {NPCMood.GUARDED, NPCMood.TENSE}:
            prefix = (
                FIRST_PREFIX
                if evidence.first_presentation
                else REPEAT_PREFIX
            )

            return f"{prefix} {get_emotion_opener(emotion)}"

    if evidence.first_presentation:
        # Keep the existing first-presentation opener.
        return None

    return REPEATED_EVIDENCE_OPENERS[evidence.character_id]


def allowed_evidence_dialogue_openers(
    character_id: str,
) -> tuple[str, ...]:

    if character_id not in NPC_IDS:
        raise ValueError("Unknown NPC")

    return (
        REPEATED_EVIDENCE_OPENERS[character_id],
        *(
            f"{prefix} {opener}"
            for prefix in (FIRST_PREFIX, REPEAT_PREFIX)
            for opener in EMOTION_OPENERS[character_id][2:]
        ),
    )
