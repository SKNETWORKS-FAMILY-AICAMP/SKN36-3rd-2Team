"""Issue #172 - bounded and authorization-aware NPC memory."""

import json
import re
from collections.abc import Sequence

from crimescene.chat.npc_dialogue_intent import (
    NPCDialogueIntent,
    classify_npc_dialogue_intent,
)
from crimescene.chat.npc_history_context import (
    MAX_HISTORY_TURNS,
    QUOTE_LINE,
    _revalidate_previous_reply,
)
from crimescene.chat.npc_session import NPCExchange
from crimescene.chat.npc_social_dialogue import (
    match_safe_social_intent,
)
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
)


MAX_SEARCH_CONTEXT_CHARS = 400
MAX_ANCHOR_QUESTION_CHARS = 200


VICTIM_RELATION_RESTATEMENT = re.compile(
    r"(?:앞에서|아까|이전에)\s*말씀하신\s*"
    r"신기범\s*씨와의\s*관계를\s*"
    r"다시\s*설명해 ?주세요[.!?~]*"
)

VICTIM_RELATION_QUESTION = re.compile(
    r"(?:신기범\s*씨를\s*어떻게\s*알고\s*계셨나요"
    r"|피해자와\s*어떤\s*관계였나요)[.!?~]*"
)

CONTEXTUAL_CLARIFICATION = re.compile(
    r"(?:방금 말씀하신 내용을\s*"
    r"(?:다시|좀 더 자세히)\s*설명해 ?주세요"
    r"|(?:그 사람|그분)에 대해\s*"
    r"방금 말씀하신 내용을\s*좀 더\s*설명해 ?주세요"
    r"|조금 더 설명해 ?주세요"
    r"|좀 더 자세히 말해 ?주세요)"
    r"[.!?~]*"
)

CANONICAL_VICTIM_QUESTION = (
    "신기범 씨를 어떻게 알고 계셨나요?"
)


def _bounded_question(question: str) -> str:
    """안전한 정규화 범위만 허용한다."""

    if not isinstance(question, str):
        return ""

    if any(c in question for c in ("\r", "\n", "\x00")):
        return ""

    normalized = " ".join(question.split())

    if len(normalized) > 120:
        return ""

    return normalized


def _is_victim_relation_restatement(question: str) -> bool:
    return VICTIM_RELATION_RESTATEMENT.fullmatch(
        _bounded_question(question)
    ) is not None


def _is_victim_relation_question(question: str) -> bool:
    normalized = _bounded_question(question)

    return (
        VICTIM_RELATION_QUESTION.fullmatch(normalized)
        is not None
        or _is_victim_relation_restatement(question)
    )


def _validate_inputs(
    question: str,
    history: Sequence[NPCExchange],
    current_revision: int,
) -> None:

    if not isinstance(question, str):
        raise TypeError("Question must be a string")

    if not question.strip():
        raise ValueError("Question cannot be empty")

    if isinstance(history, (str, bytes)) or not isinstance(
        history, Sequence
    ):
        raise TypeError("History must be a sequence")

    if type(current_revision) is not int:
        raise TypeError("Revision must be an integer")

    if current_revision < 0:
        raise ValueError("Invalid revision")


def _is_valid_exchange(
    exchange: NPCExchange,
    current_revision: int,
) -> bool:

    return (
        isinstance(exchange, NPCExchange)
        and type(exchange.state_revision) is int
        and 0 <= exchange.state_revision <= current_revision
        and isinstance(exchange.user_message, str)
        and bool(exchange.user_message.strip())
    )


def build_memory_search_query(
    question: str,
    history: Sequence[NPCExchange],
    *,
    current_revision: int,
) -> str:
    """Expand retrieval only for recognized follow-up questions.

    Historical questions remain untrusted search input.
    Historical NPC replies never become retrieval evidence.
    """

    _validate_inputs(question, history, current_revision)

    question = question.strip()

    # 명시적으로 피해자와의 관계를 재확인하는 질문은
    # 고정된 관계 질문과 원래 검색어를 함께 사용한다.
    if _is_victim_relation_restatement(question):
        expanded = f"{CANONICAL_VICTIM_QUESTION} {question}"

        if len(expanded) <= MAX_SEARCH_CONTEXT_CHARS:
            return expanded

        return question

    if classify_npc_dialogue_intent(question) is not (
        NPCDialogueIntent.FOLLOW_UP
    ):
        return question

    for exchange in reversed(history[-MAX_HISTORY_TURNS:]):

        if not _is_valid_exchange(exchange, current_revision):
            break

        previous = exchange.user_message.strip()

        if (
            len(previous) > MAX_ANCHOR_QUESTION_CHARS
            or any(c in previous for c in ("\r", "\n", "\x00"))
        ):
            break

        # Do not jump across unrelated social conversations.
        if match_safe_social_intent(previous) is not None:
            break

        intent = classify_npc_dialogue_intent(previous)

        # Resolve a bounded chain of consecutive follow-up questions.
        if intent is NPCDialogueIntent.FOLLOW_UP:
            continue

        if intent not in {
            NPCDialogueIntent.IDENTITY,
            NPCDialogueIntent.INVESTIGATION,
        }:
            break

        expanded = f"{previous} {question}"

        if len(expanded) <= MAX_SEARCH_CONTEXT_CHARS:
            return expanded

        break

    return question


def build_revalidated_repeat_output(
    question: str,
    history: Sequence[NPCExchange],
    *,
    current_revision: int,
    context: AuthorizedMultisourceContext,
) -> str | None:
    """Reconstruct quote JSON from the latest matching verified turn.

    The returned JSON must still pass the existing Output Guard.
    """

    _validate_inputs(question, history, current_revision)

    if not isinstance(context, AuthorizedMultisourceContext):
        raise TypeError("Authorized context required")

    if not context.items:
        return None

    question = question.strip()

    if classify_npc_dialogue_intent(question) not in {
        NPCDialogueIntent.IDENTITY,
        NPCDialogueIntent.INVESTIGATION,
    }:
        return None

    for exchange in reversed(history[-MAX_HISTORY_TURNS:]):

        if not _is_valid_exchange(exchange, current_revision):
            return None

        if exchange.user_message.strip() != question:
            continue

        # Never skip a newer matching refusal to restore older claims.
        if not exchange.source_ids:
            return None

        verified = _revalidate_previous_reply(exchange, context)

        if verified is None:
            return None

        quotes = []
        seen = set()

        for line in verified.splitlines()[1:]:
            match = QUOTE_LINE.fullmatch(line)

            if match is None:
                return None

            source_id = match.group("source_id")
            quote = match.group("quote")

            key = (source_id, quote)

            if key in seen:
                return None

            seen.add(key)

            quotes.append({
                "source_id": source_id,
                "quote": quote,
            })

        if not 1 <= len(quotes) <= 3:
            return None

        return json.dumps(
            {"quotes": quotes},
            ensure_ascii=False,
        )

    return None



def is_allowed_contextual_repeat(
    question: str,
    history: Sequence[NPCExchange],
    *,
    current_revision: int,
    context: AuthorizedMultisourceContext,
    reply_text: str,
    source_ids: tuple[str, ...],
) -> bool:
    """현재 승인된 동일 인용의 문맥상 재확인을 검증한다.

    과거 응답으로 신규 접근 권한을 부여하지 않는다.
    기존 Output Guard 통과 이후에만 호출한다.
    """

    _validate_inputs(question, history, current_revision)

    if not isinstance(context, AuthorizedMultisourceContext):
        return False

    if not context.items or not source_ids:
        return False

    if not history or not _bounded_question(question):
        return False

    recent = history[-MAX_HISTORY_TURNS:]

    def matches(exchange: NPCExchange) -> bool:
        return (
            _is_valid_exchange(exchange, current_revision)
            and bool(exchange.source_ids)
            and exchange.source_ids == source_ids
            and exchange.npc_message == reply_text
            and _revalidate_previous_reply(
                exchange, context
            ) == reply_text
        )

    # 피해자 관계가 명시된 재확인 질문만 제한적으로 허용한다.
    if _is_victim_relation_restatement(question):

        for exchange in reversed(recent):
            if not _is_valid_exchange(
                exchange, current_revision
            ):
                return False

            if not _is_victim_relation_question(
                exchange.user_message
            ):
                continue

            # 가장 최근 관계 질문이 차단된 경우
            # 더 오래된 응답을 복원하지 않는다.
            return matches(exchange)

        return False

    # 일반 후속 질문은 직전의 승인 응답만 재확인한다.
    # 인과관계 추론이나 새 사건 사실의 생성은 허용하지 않는다.
    if not CONTEXTUAL_CLARIFICATION.fullmatch(
        _bounded_question(question)
    ):
        return False

    if classify_npc_dialogue_intent(question) is not (
        NPCDialogueIntent.FOLLOW_UP
    ):
        return False

    expanded = build_memory_search_query(
        question,
        recent,
        current_revision=current_revision,
    )

    if expanded == question.strip():
        return False

    return matches(recent[-1])
