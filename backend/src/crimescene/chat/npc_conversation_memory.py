"""Issue #172 - bounded and authorization-aware NPC memory."""

import json
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
