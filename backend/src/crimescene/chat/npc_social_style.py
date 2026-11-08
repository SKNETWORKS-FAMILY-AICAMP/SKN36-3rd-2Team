"""CASE-001 NPC의 기본 말투와 조건부 행동을 분리한다."""

from collections.abc import Mapping
from dataclasses import dataclass, replace

from crimescene.chat.npc_persona import NPCPersona


@dataclass(frozen=True, slots=True)
class SocialStyle:
    source_anchor: str
    speaking_style: str


# 실제 CASE-001 voice 설정에서 확인한 기본 말투만 사용한다.
SOCIAL_STYLES = {
    "C01": SocialStyle(
        "침착한 정중체",
        "차분하고 간결한 정중체로 말한다.",
    ),
    "C02": SocialStyle(
        "짧고 통제된 문장",
        "짧고 통제된 존댓말을 사용한다. 감정을 쉽게 드러내지 않는다.",
    ),
    "C03": SocialStyle(
        "실무적이되 허술한 말투",
        "실무적인 존댓말을 사용하지만 표현이 다소 허술하다.",
    ),
    "C04": SocialStyle(
        "단답형",
        "짧고 건조한 존댓말을 사용한다. 필요한 말만 한다.",
    ),
    "C05": SocialStyle(
        "침착한 의료인 어투",
        "침착하고 신중한 의료인 어투로 말한다.",
    ),
    "C06": SocialStyle(
        "정중한 한국어",
        "정중한 한국어를 사용하고 단어를 신중하게 고른다.",
    ),
    "C07": SocialStyle(
        "붙임성 있는 존댓말과 농담",
        "붙임성 있는 존댓말을 사용하고 가벼운 농담을 섞는다.",
    ),
    "C08": SocialStyle(
        "마른 냉소의 존댓말",
        "짧고 건조한 존댓말을 사용한다. 불필요한 감정을 절제한다.",
    ),
    "C09": SocialStyle(
        "조심스러운 정중체",
        "조심스러운 정중체를 사용한다. 신중하게 대답한다.",
    ),
    "C10": SocialStyle(
        "빠른 말투",
        "짧고 빠르게 대답한다. 필요한 경우 상대의 질문 의도를 확인한다.",
    ),
}


def build_social_personas(
    personas: Mapping[str, NPCPersona],
    *,
    active_character_id: str,
) -> dict[str, NPCPersona]:
    """일상 대화에 필요한 기본 말투만 분리한다.

    원본 페르소나는 수정하지 않는다.
    조건부 행동은 현재 대화에 적용하지 않는다.
    """

    if not isinstance(personas, Mapping):
        raise TypeError("페르소나 목록은 매핑이어야 합니다.")

    style = SOCIAL_STYLES.get(active_character_id)

    if style is None:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    persona = personas.get(active_character_id)

    if persona is None:
        raise ValueError("등록되지 않은 NPC 페르소나입니다.")

    if not isinstance(persona, NPCPersona):
        raise TypeError("NPC 페르소나 타입이 올바르지 않습니다.")

    if persona.character_id != active_character_id:
        raise ValueError("NPC ID와 페르소나가 일치하지 않습니다.")

    social_persona = replace(
        persona,
        voice=style.speaking_style,
    )

    return {active_character_id: social_persona}
