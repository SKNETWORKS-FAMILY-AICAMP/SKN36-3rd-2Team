"""CASE-001 NPC LLM 응답의 출처 및 원문 인용 검증."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
)
from crimescene.retriever.npc_response_gate import (
    FALLBACK_REPLY,
    NPCReplyPlan,
)

MAX_OUTPUT_LENGTH = 12000
MAX_QUOTES = 3
MAX_QUOTE_LENGTH = 320
MIN_QUOTE_LENGTH = 6

QUOTE_OUTPUT_RULES = """
반드시 JSON 객체 하나만 반환하세요.

출력 형식:
{
  "quotes": [
    {
      "source_id": "승인된 근거 ID",
      "quote": "승인된 원문에서 정확히 복사한 문장"
    }
  ]
}

규칙:
1. verified_context에 존재하는 출처만 사용하세요.
2. source_id와 quote는 같은 근거에 속해야 합니다.
3. quote는 근거 원문을 그대로 복사하세요.
4. 내용을 바꾸거나 추측하지 마세요.
5. 인용은 최대 3개만 선택하세요.
6. 관련 근거가 없다면 {"quotes": []}를 반환하세요.
7. quotes 외의 필드는 출력하지 마세요.
8. 자유로운 답변이나 추가 설명을 작성하지 마세요.
""".strip()

logger = logging.getLogger(__name__)

QUOTE_RETRY_RULES = """
이전 출력이 원문 인용 검증을 통과하지 못했습니다.

반드시 다음 조건을 지키세요.

1. verified_context에 실제 존재하는 source_id만 사용하세요.
2. 해당 source_id의 원문에서 6~320자를 정확히 복사하세요.
3. 원문의 조사, 띄어쓰기, 문장부호를 수정하지 마세요.
4. 질문과 관련된 근거가 있을 때만 인용하세요.
5. JSON 객체 하나만 반환하세요.
6. 최상위 필드는 quotes 하나만 사용하세요.
7. 근거를 찾을 수 없다면 {"quotes": []}를 반환하세요.

정확히 복사할 수 없는 문장은 인용하지 마세요.
""".strip()


@dataclass(frozen=True, slots=True)
class NPCGroundedReply:
    """최종 검증을 통과한 NPC 응답."""

    text: str
    source_ids: tuple[str, ...]
    grounded: bool


def _fallback() -> NPCGroundedReply:
    """검증 실패 시 고정 응답."""

    return NPCGroundedReply(
        text=FALLBACK_REPLY,
        source_ids=(),
        grounded=False,
    )


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """JSON 중복 필드를 차단한다."""

    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError("중복된 JSON 필드입니다.")

        result[key] = value

    return result


def _is_plan_bound_to_context(
    plan: NPCReplyPlan,
    context: AuthorizedMultisourceContext,
) -> bool:
    """LLM 입력과 서버 승인 컨텍스트가 일치하는지 확인한다."""

    if not plan.can_call_llm:
        return False

    if not context.items:
        return False

    if len(plan.messages) != 2:
        return False

    system_message, user_message = plan.messages

    if system_message.get("role") != "system":
        return False

    if user_message.get("role") != "user":
        return False

    if not isinstance(system_message.get("content"), str):
        return False

    if not isinstance(user_message.get("content"), str):
        return False

    try:
        payload = json.loads(user_message["content"])
    except (ValueError, TypeError):
        return False

    if not isinstance(payload, dict):
        return False

    if payload.get("verified_context") != context.text:
        return False

    if not isinstance(payload.get("player_question"), str):
        return False

    expected_ids = tuple(item.source_id for item in context.items)

    if plan.source_ids != expected_ids:
        return False

    # 승인된 개별 근거가 전체 컨텍스트에도 포함되는지 확인
    return all(item.content in context.text for item in context.items)


def _verify_quotes(
    raw_output: str,
    context: AuthorizedMultisourceContext,
) -> tuple[tuple[str, str], ...]:
    """LLM이 선택한 인용문이 실제 승인 원문에 존재하는지 확인한다."""

    if not isinstance(raw_output, str):
        return ()

    if len(raw_output) > MAX_OUTPUT_LENGTH:
        return ()

    try:
        data = json.loads(
            raw_output,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (ValueError, TypeError):
        return ()

    if not isinstance(data, dict):
        return ()

    # 추가 필드가 있으면 거부
    if set(data) != {"quotes"}:
        return ()

    quotes = data["quotes"]

    if not isinstance(quotes, list):
        return ()

    if not 1 <= len(quotes) <= MAX_QUOTES:
        return ()

    # 동일 원본이 여러 청크로 분리됐을 수 있으므로
    # source_id별 원문 목록을 보관한다.
    authorized_sources: dict[str, list[str]] = {}

    for item in context.items:
        authorized_sources.setdefault(
            item.source_id,
            [],
        ).append(item.content)

    verified = []
    seen = set()

    for entry in quotes:
        if not isinstance(entry, dict):
            return ()

        if set(entry) != {"source_id", "quote"}:
            return ()

        source_id = entry["source_id"]
        quote = entry["quote"]

        if not isinstance(source_id, str):
            return ()

        if not isinstance(quote, str):
            return ()

        quote = quote.strip()

        if not MIN_QUOTE_LENGTH <= len(quote) <= MAX_QUOTE_LENGTH:
            return ()

        source_contents = authorized_sources.get(source_id)

        if not source_contents:
            return ()

        # 같은 출처의 승인 원문에 정확히 존재해야 한다.
        if not any(quote in content for content in source_contents):
            return ()

        key = (source_id, quote)

        if key in seen:
            return ()

        seen.add(key)
        verified.append(key)

    return tuple(verified)


def _quote_failure_reason(
    raw_output: str,
    context: AuthorizedMultisourceContext,
) -> str:
    """LLM 인용 검증 실패 원인을 텍스트 노출 없이 분류한다."""

    if not isinstance(raw_output, str):
        return "INVALID_OUTPUT_TYPE"

    if len(raw_output) > MAX_OUTPUT_LENGTH:
        return "OUTPUT_TOO_LONG"

    try:
        data = json.loads(
            raw_output,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (ValueError, TypeError):
        return "INVALID_JSON"

    if not isinstance(data, dict) or set(data) != {"quotes"}:
        return "INVALID_JSON_SCHEMA"

    quotes = data["quotes"]

    if not isinstance(quotes, list):
        return "INVALID_QUOTES_TYPE"

    if not quotes:
        return "EMPTY_QUOTES"

    if len(quotes) > MAX_QUOTES:
        return "TOO_MANY_QUOTES"

    allowed = {}

    for item in context.items:
        allowed.setdefault(
            item.source_id,
            [],
        ).append(item.content)

    seen = set()

    for entry in quotes:
        if not isinstance(entry, dict):
            return "INVALID_QUOTE_ENTRY"

        if set(entry) != {"source_id", "quote"}:
            return "INVALID_QUOTE_FIELDS"

        source_id = entry["source_id"]
        quote = entry["quote"]

        if not isinstance(source_id, str):
            return "INVALID_SOURCE_ID"

        if not isinstance(quote, str):
            return "INVALID_QUOTE_TYPE"

        quote = quote.strip()

        if source_id not in allowed:
            return "UNAUTHORIZED_SOURCE"

        if not MIN_QUOTE_LENGTH <= len(quote) <= MAX_QUOTE_LENGTH:
            return "INVALID_QUOTE_LENGTH"

        if not any(quote in content for content in allowed[source_id]):
            return "QUOTE_NOT_IN_SOURCE"

        key = (source_id, quote)

        if key in seen:
            return "DUPLICATE_QUOTE"

        seen.add(key)

    return "UNKNOWN_VALIDATION_FAILURE"


def run_grounded_npc_response(
    plan: NPCReplyPlan,
    authorized_context: AuthorizedMultisourceContext,
    *,
    generate: Callable[[list[dict[str, str]]], str],
) -> NPCGroundedReply:
    """LLM 인용 검증 및 최대 1회 재시도."""

    if not isinstance(plan, NPCReplyPlan):
        raise TypeError("NPCReplyPlan이 필요합니다.")

    if not isinstance(
        authorized_context,
        AuthorizedMultisourceContext,
    ):
        raise TypeError("AuthorizedMultisourceContext가 필요합니다.")

    if not callable(generate):
        raise TypeError("LLM 생성 함수가 필요합니다.")

    # 1. LLM 입력과 접근 승인 근거 일치 검사
    if not _is_plan_bound_to_context(
        plan,
        authorized_context,
    ):
        logger.warning("NPC 답변 차단: PLAN_CONTEXT_MISMATCH")
        return _fallback()

    # 2. 기존 시스템 프롬프트 및 인용 규칙 유지
    messages = [dict(message) for message in plan.messages]

    messages[0]["content"] += "\n\n" + QUOTE_OUTPUT_RULES

    # 3. 첫 번째 Ollama 호출
    raw_output = generate(messages)

    verified = _verify_quotes(
        raw_output,
        authorized_context,
    )

    # 4. 검증 실패 시 원인 기록 및 1회 재시도
    if not verified:
        reason = _quote_failure_reason(
            raw_output,
            authorized_context,
        )

        logger.warning(
            "NPC 인용 검증 실패: %s / 재시도 1회",
            reason,
        )

        retry_messages = [dict(message) for message in messages]

        retry_messages[0]["content"] += "\n\n" + QUOTE_RETRY_RULES

        raw_output = generate(retry_messages)

        verified = _verify_quotes(
            raw_output,
            authorized_context,
        )

        if not verified:
            reason = _quote_failure_reason(
                raw_output,
                authorized_context,
            )

            logger.warning(
                "NPC 인용 재검증 실패: %s",
                reason,
            )

            return _fallback()

    # 5. 서버가 검증한 인용문만 최종 응답으로 구성
    lines = [
        "제가 확인한 자료에는 이렇게 나와 있어요.",
    ]

    source_ids = []

    for source_id, quote in verified:
        lines.append(f"“{quote}” (근거: {source_id})")

        if source_id not in source_ids:
            source_ids.append(source_id)

    logger.info(
        "NPC 근거 검증 성공: 출처 %d개",
        len(source_ids),
    )

    return NPCGroundedReply(
        text="\n".join(lines),
        source_ids=tuple(source_ids),
        grounded=True,
    )
