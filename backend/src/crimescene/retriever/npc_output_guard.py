"""CASE-001 NPC LLM 응답의 출처 및 원문 인용 검증."""

import json
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


def run_grounded_npc_response(
    plan: NPCReplyPlan,
    authorized_context: AuthorizedMultisourceContext,
    *,
    generate: Callable[[list[dict[str, str]]], str],
) -> NPCGroundedReply:
    """검증된 근거에서 LLM이 선택한 인용문으로 NPC 응답을 만든다.

    동작:
        1. NPC 응답 계획 검증
        2. 승인된 컨텍스트 일치 확인
        3. LLM에 JSON 인용문 선택 요청
        4. 출처 ID 검증
        5. 원문 인용문 검증
        6. 서버가 최종 응답 생성

    보안:
        LLM이 만든 자유로운 답변은 그대로 반환하지 않는다.
        검증된 원문 인용문만 최종 응답에 포함한다.
    """

    if not isinstance(plan, NPCReplyPlan):
        raise TypeError("NPCReplyPlan이 필요합니다.")

    if not isinstance(
        authorized_context,
        AuthorizedMultisourceContext,
    ):
        raise TypeError("AuthorizedMultisourceContext가 필요합니다.")

    if not callable(generate):
        raise TypeError("LLM 생성 함수가 필요합니다.")

    # --------------------------------------------------
    # 1. 근거 없는 응답 차단
    # --------------------------------------------------

    if not _is_plan_bound_to_context(
        plan,
        authorized_context,
    ):
        return _fallback()

    # --------------------------------------------------
    # 2. LLM 입력 구성
    # --------------------------------------------------

    messages = [dict(message) for message in plan.messages]

    messages[0]["content"] += "\n\n" + QUOTE_OUTPUT_RULES

    # --------------------------------------------------
    # 3. LLM 호출
    # --------------------------------------------------

    raw_output = generate(messages)

    # --------------------------------------------------
    # 4. 생성 결과 검증
    # --------------------------------------------------

    verified = _verify_quotes(
        raw_output,
        authorized_context,
    )

    if not verified:
        return _fallback()

    # --------------------------------------------------
    # 5. 서버가 검증된 인용문만 출력
    # --------------------------------------------------

    lines = [
        "제가 확인한 자료에는 이렇게 나와 있어요.",
    ]

    source_ids = []

    for source_id, quote in verified:
        lines.append(f"“{quote}” (근거: {source_id})")

        if source_id not in source_ids:
            source_ids.append(source_id)

    return NPCGroundedReply(
        text="\n".join(lines),
        source_ids=tuple(source_ids),
        grounded=True,
    )
