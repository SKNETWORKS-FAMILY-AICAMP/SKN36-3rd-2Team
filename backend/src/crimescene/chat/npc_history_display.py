"""저장된 NPC 대화를 출처 노출 없이 화면용 대사로 변환합니다.

원본/출처는 DB에 보존하며, 저장 시 승인된 인용문만 표시합니다.
"""

from collections.abc import Sequence

from crimescene.chat.npc_natural_reply import LEGACY_HEADER, QUOTE_PATTERN
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY


def render_stored_npc_message(
    message: str,
    source_ids: Sequence[str],
) -> str:
    """검증 후 저장된 대화의 내부 인용 형식을 화면에서 제거합니다.

    저장된 인용의 출처 목록까지 재검사합니다. 허용되지 않는 형식이면
    원문을 출력하지 않고 안전한 기본 응답을 반환합니다.
    """
    if not isinstance(message, str) or not message.strip():
        return FALLBACK_REPLY

    if not isinstance(source_ids, (tuple, list)) or any(
        not isinstance(source_id, str) or not source_id for source_id in source_ids
    ):
        return FALLBACK_REPLY

    # 안전한 일반 대화 및 근거 부족 응답은 원래 형식을 유지합니다.
    if not source_ids:
        if LEGACY_HEADER in message or "(근거:" in message:
            return FALLBACK_REPLY
        return message

    lines = message.splitlines()
    if not 2 <= len(lines) <= 4 or lines[0] != LEGACY_HEADER:
        return FALLBACK_REPLY

    quotes: list[str] = []
    observed_sources: list[str] = []

    for line in lines[1:]:
        match = QUOTE_PATTERN.fullmatch(line)
        if match is None:
            return FALLBACK_REPLY

        quote = match.group("quote")
        source_id = match.group("source_id")
        if not 6 <= len(quote) <= 320:
            return FALLBACK_REPLY

        quotes.append(quote)
        if source_id not in observed_sources:
            observed_sources.append(source_id)

    if tuple(observed_sources) != tuple(source_ids):
        return FALLBACK_REPLY

    # 메타데이터 없는 NPC 대사만 전송합니다. 내용은 재작성하지 않습니다.
    return "\n".join(quotes)
