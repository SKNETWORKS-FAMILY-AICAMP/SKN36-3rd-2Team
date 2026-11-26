"""Issue #172 - conversation memory validation."""

import json

import pytest

from crimescene.chat.npc_conversation_memory import (
    build_memory_search_query,
    build_revalidated_repeat_output,
)
from crimescene.chat.npc_session import NPCExchange
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
    AuthorizedMultisourceItem,
)
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY


QUESTION = "피해자와 어떤 관계였나요?"
FOLLOW_UP = "방금 말씀하신 내용을 좀 더 자세히 설명해 주세요."
QUOTE = "당시 서로 의견이 달랐습니다."
SOURCE = "K-C01-02"


def make_context():
    return AuthorizedMultisourceContext(
        items=(
            AuthorizedMultisourceItem(
                kind="chunk",
                item_id="MEMORY-TEST",
                source_id=SOURCE,
                score=0.1,
                methods=("dense",),
                content=QUOTE,
                truth_status="character_claim",
            ),
        ),
        text=QUOTE,
    )


def exchange(
    question=QUESTION,
    *,
    quote=QUOTE,
    source=SOURCE,
    revision=0,
):
    return NPCExchange(
        user_message=question,
        npc_message=(
            "제가 확인한 자료에는 이렇게 나와 있어요.\n"
            f"“{quote}” (근거: {source})"
        ),
        source_ids=(source,),
        state_revision=revision,
    )


def fallback_exchange(question=QUESTION, revision=0):
    return NPCExchange(
        user_message=question,
        npc_message=FALLBACK_REPLY,
        source_ids=(),
        state_revision=revision,
    )


def search(question, history, revision=2):
    return build_memory_search_query(
        question,
        history,
        current_revision=revision,
    )


def repeat(question, history, revision=2):
    return build_revalidated_repeat_output(
        question,
        history,
        current_revision=revision,
        context=make_context(),
    )


def test_followup_uses_previous_question():
    assert search(FOLLOW_UP, [exchange()]) == (
        f"{QUESTION} {FOLLOW_UP}"
    )


def test_followup_after_fallback_still_uses_question():
    assert search(FOLLOW_UP, [fallback_exchange()]) == (
        f"{QUESTION} {FOLLOW_UP}"
    )


def test_followup_chain_uses_concrete_anchor():
    history = [
        exchange(),
        exchange("그게 무슨 뜻이죠?"),
        exchange("그 이후에는요?"),
    ]

    assert search(FOLLOW_UP, history) == (
        f"{QUESTION} {FOLLOW_UP}"
    )


def test_previous_npc_reply_never_enters_search():
    history = [
        exchange(
            quote="PRIVATE_REPLY_SENTINEL",
            source="ADMIN-SECRET",
        )
    ]

    result = search(FOLLOW_UP, history)

    assert QUESTION in result
    assert "PRIVATE_REPLY_SENTINEL" not in result
    assert "ADMIN-SECRET" not in result


@pytest.mark.parametrize(
    "question",
    [
        QUESTION,
        "본인에 대해서 간단하게 소개해 주세요.",
        "제가 아까 어떤 질문을 했는지 기억하세요?",
        "혹시 저한테 숨기고 있는 게 있으세요?",
    ],
)
def test_non_followup_search_is_unchanged(question):
    assert search(question, [exchange()]) == question


@pytest.mark.parametrize(
    "history",
    [
        [],
        [exchange(revision=99)],
        [exchange(question="a" * 201)],
        [exchange(question="질문\n다른 질문")],
        [exchange(), fallback_exchange("안녕하세요.")],
        [exchange(), fallback_exchange("솔직히 말씀하세요.")],
        [
            exchange(),
            fallback_exchange("제가 아까 어떤 질문을 했는지 기억하세요?"),
        ],
    ],
)
def test_missing_or_invalid_anchor_is_not_used(history):
    assert search(FOLLOW_UP, history) == FOLLOW_UP


def test_history_window_is_bounded():
    history = [
        exchange(),
        *[
            fallback_exchange("그게 무슨 뜻이죠?")
            for _ in range(4)
        ],
    ]

    assert search(FOLLOW_UP, history) == FOLLOW_UP


def test_exact_repeat_reconstructs_verified_json():
    output = repeat(QUESTION, [exchange()])

    assert json.loads(output) == {
        "quotes": [
            {
                "source_id": SOURCE,
                "quote": QUOTE,
            }
        ]
    }


@pytest.mark.parametrize(
    "history",
    [
        [],
        [exchange(question="다른 질문입니다.")],
        [exchange(source="K-C02-PRIVATE")],
        [exchange(quote="현재 승인되지 않은 원문입니다.")],
        [exchange(revision=99)],
        [fallback_exchange()],
        [exchange(), fallback_exchange(revision=1)],
    ],
)
def test_invalid_or_superseded_repeat_is_rejected(history):
    assert repeat(QUESTION, history) is None


def test_followup_is_not_replayed_as_exact_repeat():
    assert repeat(
        FOLLOW_UP,
        [exchange(question=FOLLOW_UP)],
    ) is None


def test_latest_matching_reply_takes_priority():
    history = [
        exchange(revision=0),
        exchange(
            revision=1,
            quote="이전 진술과 다른 미승인 내용입니다.",
        ),
    ]

    assert repeat(QUESTION, history) is None


def test_no_context_cannot_replay():
    context = AuthorizedMultisourceContext(
        items=(),
        text="",
    )

    result = build_revalidated_repeat_output(
        QUESTION,
        [exchange()],
        current_revision=2,
        context=context,
    )

    assert result is None


def test_invalid_revision_type_is_rejected():
    with pytest.raises(TypeError):
        search(FOLLOW_UP, [exchange()], revision=True)


def test_memory_input_is_not_mutated():
    history = [exchange()]
    before = history.copy()

    search(FOLLOW_UP, history)
    repeat(QUESTION, history)

    assert history == before
