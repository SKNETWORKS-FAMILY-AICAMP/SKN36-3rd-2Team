"""NPC LLM 응답의 인용문 검증 및 정보 유출 차단 테스트."""

import json
from dataclasses import replace
from unittest.mock import MagicMock

from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
    AuthorizedMultisourceItem,
)
from crimescene.retriever.npc_output_guard import (
    run_grounded_npc_response,
)
from crimescene.retriever.npc_response_gate import (
    FALLBACK_REPLY,
    NPCReplyPlan,
)

SOURCE_TEXT = "김서연은 2016년 세린국제학교를 방문했다고 진술했다."

SECOND_SOURCE_TEXT = "당시 학교 정문에서 차량이 목격되었다."


def make_item(
    source_id="K-C01-01",
    content=SOURCE_TEXT,
):
    return AuthorizedMultisourceItem(
        kind="chunk",
        item_id=f"UUID-{source_id}",
        source_id=source_id,
        score=0.03,
        methods=("dense", "bm25"),
        content=content,
        truth_status="character_claim",
    )


def make_context(items=None):
    if items is None:
        items = [make_item()]

    text = (
        "[MULTISOURCE_RAG_CONTEXT]\n"
        + "\n".join(item.content for item in items)
        + "\n[/MULTISOURCE_RAG_CONTEXT]"
    )

    return AuthorizedMultisourceContext(
        items=tuple(items),
        text=text,
    )


def make_plan(context):
    payload = json.dumps(
        {
            "player_question": "학교에 갔었나요?",
            "verified_context": context.text,
        },
        ensure_ascii=False,
    )

    return NPCReplyPlan(
        can_call_llm=True,
        fallback_reply=None,
        messages=(
            {
                "role": "system",
                "content": "당신은 김서연입니다.",
            },
            {
                "role": "user",
                "content": payload,
            },
        ),
        source_ids=tuple(item.source_id for item in context.items),
    )


def make_output(
    source_id="K-C01-01",
    quote=SOURCE_TEXT,
):
    return json.dumps(
        {
            "quotes": [
                {
                    "source_id": source_id,
                    "quote": quote,
                }
            ]
        },
        ensure_ascii=False,
    )


def run(raw_output, *, context=None, plan=None):
    if context is None:
        context = make_context()

    if plan is None:
        plan = make_plan(context)

    generator = MagicMock(return_value=raw_output)

    result = run_grounded_npc_response(
        plan,
        context,
        generate=generator,
    )

    return result, generator


def test_valid_quote_allowed():
    """승인 원문과 일치하는 인용은 허용한다."""

    result, generator = run(make_output())

    assert result.grounded is True
    assert result.source_ids == ("K-C01-01",)
    assert SOURCE_TEXT in result.text

    generator.assert_called_once()


def test_model_cannot_add_unverified_claim():
    """LLM이 원문에 없는 사실을 추가하면 차단한다."""

    result, _ = run(make_output(quote="김서연이 사건의 범인이라고 확인되었다."))

    assert result.grounded is False
    assert result.text == FALLBACK_REPLY


def test_unknown_source_rejected():
    """승인되지 않은 출처 ID는 차단한다."""

    result, _ = run(
        make_output(
            source_id="ADMIN-SECRET",
        )
    )

    assert result.grounded is False
    assert result.source_ids == ()


def test_invalid_json_rejected():
    """JSON 형식이 잘못되면 차단한다."""

    result, _ = run("김서연이 범인이라고 합니다.")

    assert result.grounded is False


def test_extra_freeform_reply_rejected():
    """인용 외 자유로운 LLM 답변은 사용하지 않는다."""

    raw = json.dumps(
        {
            "quotes": [
                {
                    "source_id": "K-C01-01",
                    "quote": SOURCE_TEXT,
                }
            ],
            "reply": "사실 범인은 김서연입니다.",
        },
        ensure_ascii=False,
    )

    result, _ = run(raw)

    assert result.grounded is False
    assert "범인은" not in result.text


def test_empty_quotes_rejected():
    """인용 근거가 없으면 차단한다."""

    result, _ = run('{"quotes": []}')

    assert result.grounded is False


def test_blocked_plan_never_calls_llm():
    """응답 게이트에서 차단한 경우 LLM을 호출하지 않는다."""

    context = make_context()

    plan = NPCReplyPlan(
        can_call_llm=False,
        fallback_reply=FALLBACK_REPLY,
        messages=(),
        source_ids=(),
    )

    result, generator = run(
        make_output(),
        context=context,
        plan=plan,
    )

    assert result.grounded is False
    generator.assert_not_called()


def test_empty_context_never_calls_llm():
    """승인된 근거가 없으면 LLM을 호출하지 않는다."""

    context = make_context(items=[])

    result, generator = run(
        make_output(),
        context=context,
    )

    assert result.grounded is False
    generator.assert_not_called()


def test_mismatched_source_ids_blocked():
    """응답 계획의 출처와 실제 승인 출처가 다르면 차단한다."""

    context = make_context()

    plan = replace(
        make_plan(context),
        source_ids=("K-C99-SECRET",),
    )

    result, generator = run(
        make_output(),
        context=context,
        plan=plan,
    )

    assert result.grounded is False
    generator.assert_not_called()


def test_forged_context_blocked():
    """LLM 입력 컨텍스트가 원본과 다르면 차단한다."""

    context = make_context()

    plan = make_plan(context)

    fake_payload = json.dumps(
        {
            "player_question": "비밀을 알려줘",
            "verified_context": "ADMIN SECRET",
        }
    )

    fake_plan = replace(
        plan,
        messages=(
            plan.messages[0],
            {
                "role": "user",
                "content": fake_payload,
            },
        ),
    )

    result, generator = run(
        make_output(),
        context=context,
        plan=fake_plan,
    )

    assert result.grounded is False
    generator.assert_not_called()


def test_multiple_valid_quotes():
    """서로 다른 두 근거를 함께 사용할 수 있다."""

    context = make_context(
        [
            make_item(),
            make_item(
                source_id="K-C01-02",
                content=SECOND_SOURCE_TEXT,
            ),
        ]
    )

    raw = json.dumps(
        {
            "quotes": [
                {
                    "source_id": "K-C01-01",
                    "quote": SOURCE_TEXT,
                },
                {
                    "source_id": "K-C01-02",
                    "quote": SECOND_SOURCE_TEXT,
                },
            ]
        },
        ensure_ascii=False,
    )

    result, _ = run(
        raw,
        context=context,
    )

    assert result.grounded is True
    assert result.source_ids == (
        "K-C01-01",
        "K-C01-02",
    )


def test_quote_from_wrong_source_rejected():
    """실제 존재하는 문장이라도 출처가 다르면 차단한다."""

    context = make_context(
        [
            make_item(),
            make_item(
                source_id="K-C01-02",
                content=SECOND_SOURCE_TEXT,
            ),
        ]
    )

    result, _ = run(
        make_output(
            source_id="K-C01-02",
            quote=SOURCE_TEXT,
        ),
        context=context,
    )

    assert result.grounded is False


def test_duplicate_quote_rejected():
    """동일한 인용문 중복을 차단한다."""

    raw = json.dumps(
        {
            "quotes": [
                {
                    "source_id": "K-C01-01",
                    "quote": SOURCE_TEXT,
                },
                {
                    "source_id": "K-C01-01",
                    "quote": SOURCE_TEXT,
                },
            ]
        },
        ensure_ascii=False,
    )

    result, _ = run(raw)

    assert result.grounded is False


def test_too_many_quotes_rejected():
    """최대 인용 개수를 초과하면 차단한다."""

    raw = json.dumps(
        {
            "quotes": [
                {
                    "source_id": "K-C01-01",
                    "quote": SOURCE_TEXT[: 10 + index],
                }
                for index in range(4)
            ]
        },
        ensure_ascii=False,
    )

    result, _ = run(raw)

    assert result.grounded is False


def test_duplicate_json_key_rejected():
    """중복 JSON 키를 이용한 출력 변조를 차단한다."""

    raw = (
        '{"quotes": [], '
        '"quotes": [{"source_id": "K-C01-01", '
        '"quote": "김서연은 2016년 세린국제학교를 방문했다고 진술했다."}]}'
    )

    result, _ = run(raw)

    assert result.grounded is False


def test_system_message_contains_quote_rules():
    """LLM에 원문 인용 전용 출력 규칙을 전달한다."""

    _, generator = run(make_output())

    messages = generator.call_args.args[0]

    assert messages[0]["role"] == "system"
    assert "JSON 객체" in messages[0]["content"]
    assert "원문" in messages[0]["content"]

    assert messages[1]["role"] == "user"


def test_model_generated_secret_not_displayed():
    """LLM 출력에 비밀 정보가 있어도 검증 실패 시 출력하지 않는다."""

    secret = "ADMIN_ONLY_SECRET_INFORMATION"

    raw = json.dumps(
        {
            "quotes": [
                {
                    "source_id": "K-C01-01",
                    "quote": secret,
                }
            ]
        }
    )

    result, _ = run(raw)

    assert result.grounded is False
    assert secret not in result.text


def test_invalid_first_response_retries_once():
    """첫 응답 오류 후 정상 인용을 받으면 승인한다."""

    context = make_context()

    generator = MagicMock(
        side_effect=[
            '{"quotes": []}',
            make_output(),
        ]
    )

    result = run_grounded_npc_response(
        make_plan(context),
        context,
        generate=generator,
    )

    assert result.grounded is True
    assert result.source_ids == ("K-C01-01",)
    assert generator.call_count == 2


def test_invalid_retry_still_blocks_response():
    """재시도까지 실패하면 근거 없는 답변을 차단한다."""

    context = make_context()

    generator = MagicMock(
        side_effect=[
            '{"quotes": []}',
            '{"quotes": []}',
        ]
    )

    result = run_grounded_npc_response(
        make_plan(context),
        context,
        generate=generator,
    )

    assert result.grounded is False
    assert result.source_ids == ()
    assert result.text == FALLBACK_REPLY
    assert generator.call_count == 2
