"""Issue #174 - canonical quote format regression."""

import json
from unittest.mock import MagicMock

import pytest

from crimescene.retriever import npc_output_guard as guard
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
    AuthorizedMultisourceItem,
)
from crimescene.retriever.npc_response_gate import (
    FALLBACK_REPLY,
    NPCReplyPlan,
)

FIRST = "첫 번째 승인된 기록입니다."
SECOND = "두 번째 승인된 기록입니다."
SOURCE_ID = "TEST-SOURCE-174"


def make_context(content, source_id=SOURCE_ID):
    item = AuthorizedMultisourceItem(
        kind="chunk",
        item_id="TEST-UUID",
        source_id=source_id,
        score=0.1,
        methods=("dense",),
        content=content,
        truth_status="character_claim",
    )

    return AuthorizedMultisourceContext(
        items=(item,),
        text=f"[SOURCE 1]\n{content}\n[/SOURCE]",
    )


def make_plan(context):
    return NPCReplyPlan(
        can_call_llm=True,
        fallback_reply=None,
        source_ids=tuple(
            item.source_id for item in context.items
        ),
        authorized_context=context,
        messages=(
            {
                "role": "system",
                "content": "승인된 원문만 인용하세요.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "player_question": "자료를 설명해 주세요.",
                        "verified_context": context.text,
                    },
                    ensure_ascii=False,
                ),
            },
        ),
    )


def output(quote, source_id=SOURCE_ID):
    return json.dumps(
        {
            "quotes": [{
                "source_id": source_id,
                "quote": quote,
            }]
        },
        ensure_ascii=False,
    )


@pytest.mark.parametrize(
    "separator",
    [
        "\n",
        "\r",
        "\r\n",
        "\v",
        "\f",
        "\x1c",
        "\x1d",
        "\x1e",
        "\x85",
        "\u2028",
        "\u2029",
    ],
)
def test_multiline_quotes_rejected(separator):
    quote = FIRST + separator + SECOND
    context = make_context(quote)

    assert guard._verify_quotes(
        output(quote), context
    ) == ()

    assert guard._quote_failure_reason(
        output(quote), context
    ) == "INVALID_QUOTE_FORMAT"


@pytest.mark.parametrize(
    "quote",
    [
        "승인된 기록입니다. (근거: OTHER)",
        "제가 확인한 자료에는 이렇게 나와 있어요.",
    ],
)
def test_reserved_quote_markers_rejected(quote):
    context = make_context(quote)

    assert guard._verify_quotes(
        output(quote), context
    ) == ()

    assert guard._quote_failure_reason(
        output(quote), context
    ) == "INVALID_QUOTE_FORMAT"


@pytest.mark.parametrize(
    "source_id",
    ["", "SOURCE)", "SOURCE\nOTHER", "SOURCE\u2028OTHER"],
)
def test_invalid_source_delimiters(source_id):
    context = make_context(FIRST, source_id)

    assert guard._verify_quotes(
        output(FIRST, source_id), context
    ) == ()

    assert guard._quote_failure_reason(
        output(FIRST, source_id), context
    ) == "INVALID_SOURCE_ID"


def test_single_line_from_multiline_source_allowed():
    context = make_context(FIRST + "\n" + SECOND)

    assert guard._verify_quotes(
        output(FIRST), context
    ) == ((SOURCE_ID, FIRST),)


def test_joined_lines_rejected():
    context = make_context(FIRST + "\n" + SECOND)
    forged = FIRST + " " + SECOND

    assert guard._verify_quotes(
        output(forged), context
    ) == ()

    assert guard._quote_failure_reason(
        output(forged), context
    ) == "QUOTE_NOT_IN_SOURCE"


def test_multiline_retry_recovers_valid_quote():
    original = FIRST + "\n" + SECOND
    context = make_context(original)

    generate = MagicMock(
        side_effect=[
            output(original),
            output(FIRST),
        ]
    )

    reply = guard.run_grounded_npc_response(
        make_plan(context),
        context,
        generate=generate,
        retry_empty_quotes=False,
    )

    assert reply.grounded
    assert reply.source_ids == (SOURCE_ID,)
    assert FIRST in reply.text
    assert SECOND not in reply.text
    assert generate.call_count == 2

    retry_prompt = generate.call_args.args[0][0]["content"]

    assert "줄바꿈 없는 단일 행" in retry_prompt


def test_repeated_multiline_failure_returns_safe_fallback():
    original = FIRST + "\n" + SECOND
    context = make_context(original)

    generate = MagicMock(
        return_value=output(original)
    )

    reply = guard.run_grounded_npc_response(
        make_plan(context),
        context,
        generate=generate,
        retry_empty_quotes=False,
    )

    assert not reply.grounded
    assert reply.source_ids == ()
    assert reply.text == FALLBACK_REPLY
    assert generate.call_count == 2


def test_empty_quotes_still_skips_retry():
    context = make_context(FIRST)

    generate = MagicMock(
        return_value='{"quotes": []}'
    )

    reply = guard.run_grounded_npc_response(
        make_plan(context),
        context,
        generate=generate,
        retry_empty_quotes=False,
    )

    assert not reply.grounded
    assert reply.source_ids == ()
    assert reply.text == FALLBACK_REPLY

    generate.assert_called_once()
