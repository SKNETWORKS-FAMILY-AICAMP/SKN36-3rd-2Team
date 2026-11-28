"""Source-bound natural speech pilot."""

import os

from types import MappingProxyType

from crimescene.chat.npc_speech_catalog import (
    configured_speech_catalog,
)

from crimescene.chat.npc_natural_reply import (
    LEGACY_HEADER,
    QUOTE_PATTERN,
)


# NPC + 출처 ID + 정확한 승인 인용문을 함께 검증한다.
# 스토리 담당자 검수 전까지 실험 기능으로만 사용한다.

SPEECH_VARIANTS = MappingProxyType({
    (
        "C01",
        "K-C01-01",
        "재단 이사장이다. 후원 재단 이사장이자 옛 교사로 동창회에 왔다.",
    ): (
        "지금은 후원 재단 이사장으로 일하고 있습니다. "
        "예전에는 교사였고, 이번 동창회에 참석했지요."
    ),

    (
        "C03",
        "K-C03-01",
        "부동산·시설 운영 회사 후계자다.",
    ): (
        "저는 부동산하고 시설 운영 쪽 회사의 후계자입니다."
    ),

    (
        "C03",
        "K-C03-01",
        "부동산·시설 운영 회사 후계자다. "
        "동창으로서 자기 회사로 동창회 시설을 협찬했고 "
        "시설 점검을 맡았다.",
    ): (
        "부동산하고 시설 운영 쪽 회사의 후계자입니다. "
        "동창으로 참석했고, 저희 회사에서 행사 시설을 "
        "협찬했습니다. 시설 점검도 제가 맡았고요."
    ),

    (
        "C07",
        "K-C07-01",
        "물류·전시 회사 후계자이고 동창으로 참석했다.",
    ): (
        "저는 물류하고 전시 쪽 회사의 후계자예요. "
        "이번에는 동창으로 참석했고요."
    ),

    (
        "C07",
        "K-C07-02",
        "자기 물류 회사가 신기범에게 소포를 운송했다. "
        "내용물은 모르고 오래된 학교 자료라고만 들었다.",
    ): (
        "아, 기범이요? 저희 물류 회사에서 "
        "그 사람한테 소포를 운송한 적이 있어요. "
        "오래된 학교 자료라고만 들었고, "
        "정확한 내용물은 몰라요."
    ),
})


def pilot_speech_enabled() -> bool:
    return os.getenv(
        "CRIMESCENE_ENABLE_PILOT_SPEECH", "false"
    ).lower() in {"true", "1", "yes"}


def render_pilot_speech(
    canonical_text: str,
    source_ids,
    character_id: str,
) -> str | None:
    """검증 가능한 인용문만 자연어 대사로 전환한다."""

    if not isinstance(canonical_text, str):
        return None

    if not isinstance(source_ids, (tuple, list)):
        return None

    if not source_ids:
        return None

    lines = canonical_text.splitlines()

    if (
        not 2 <= len(lines) <= 4
        or lines[0] != LEGACY_HEADER
    ):
        return None

    try:
        catalog = configured_speech_catalog()
    except (OSError, ValueError, TypeError):
        # 설정 또는 무결성 검증 실패 시 기존 인용문으로 복귀
        return None

    variants = (
        catalog
        if catalog is not None
        else SPEECH_VARIANTS
    )

    rendered = []
    observed_sources = []

    for line in lines[1:]:
        match = QUOTE_PATTERN.fullmatch(line)

        if match is None:
            return None

        source_id = match.group("source_id")
        quote = match.group("quote")

        speech = variants.get(
            (character_id, source_id, quote)
        )

        # 일부 근거만 임의로 생략하지 않는다.
        if speech is None:
            return None

        if source_id not in observed_sources:
            observed_sources.append(source_id)

        if speech not in rendered:
            rendered.append(speech)

    if tuple(observed_sources) != tuple(source_ids):
        return None

    return " ".join(rendered)
