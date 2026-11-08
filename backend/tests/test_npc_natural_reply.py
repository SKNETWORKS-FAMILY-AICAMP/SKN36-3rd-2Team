"""Issue #25 - 자연스러운 NPC 말풍선 검증."""

from crimescene.chat.npc_natural_reply import render_npc_speech
from crimescene.chat.npc_reaction import NPCReaction
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
    AuthorizedMultisourceItem,
)
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY

SOURCE_ID = "K-C01-05"

QUOTE = (
    "말이 높아진 건 맞습니다. "
    "제가 서두르지 말자고 했고, "
    "그는 은폐하려 한다며 화를 냈습니다."
)


def make_context():
    item = AuthorizedMultisourceItem(
        kind="chunk",
        item_id="TEST-UUID",
        source_id=SOURCE_ID,
        score=0.1,
        methods=("dense",),
        content=QUOTE,
        truth_status="character_claim",
    )

    return AuthorizedMultisourceContext(
        items=(item,),
        text=QUOTE,
    )


def make_reply():
    return NPCGroundedReply(
        text=(
            f"제가 확인한 자료에는 이렇게 나와 있어요.\n“{QUOTE}” (근거: {SOURCE_ID})"
        ),
        source_ids=(SOURCE_ID,),
        grounded=True,
    )


def make_reaction(
    character_id="C01",
    mode="neutral",
):
    return NPCReaction(
        character_id=character_id,
        mode=mode,
        repeat_count=0,
        evidence_presented=False,
    )


def test_c01_speaks_naturally():
    text = render_npc_speech(
        make_reply(),
        context=make_context(),
        reaction=make_reaction(),
    )

    assert text == QUOTE
    assert "제가 확인한 자료에는" not in text
    assert "(근거:" not in text


def test_character_style_changes():
    c01 = render_npc_speech(
        make_reply(),
        context=make_context(),
        reaction=make_reaction("C01"),
    )

    c02 = render_npc_speech(
        make_reply(),
        context=make_context(),
        reaction=make_reaction("C02"),
    )

    assert c01 != c02
    assert QUOTE in c01
    assert QUOTE in c02


def test_repeated_question_changes_expression():
    text = render_npc_speech(
        make_reply(),
        context=make_context(),
        reaction=make_reaction("C01", "repeated"),
    )

    assert "다시 말씀드리겠습니다." in text
    assert QUOTE in text


def test_unauthorized_quote_is_blocked():
    reply = NPCGroundedReply(
        text=(
            "제가 확인한 자료에는 이렇게 나와 있어요.\n"
            "“승인되지 않은 사건의 비밀입니다.” "
            f"(근거: {SOURCE_ID})"
        ),
        source_ids=(SOURCE_ID,),
        grounded=True,
    )

    text = render_npc_speech(
        reply,
        context=make_context(),
        reaction=make_reaction(),
    )

    assert text == FALLBACK_REPLY
    assert "승인되지 않은" not in text


def test_source_mismatch_is_blocked():
    reply = NPCGroundedReply(
        text=make_reply().text,
        source_ids=("ADMIN-SECRET",),
        grounded=True,
    )

    text = render_npc_speech(
        reply,
        context=make_context(),
        reaction=make_reaction(),
    )

    assert text == FALLBACK_REPLY


def test_fallback_does_not_create_new_facts():
    reply = NPCGroundedReply(
        text=FALLBACK_REPLY,
        source_ids=(),
        grounded=False,
    )

    text = render_npc_speech(
        reply,
        context=make_context(),
        reaction=make_reaction(),
    )

    assert text == FALLBACK_REPLY
