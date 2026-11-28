"""Source-bound speech rendering security regression."""

import pytest

from crimescene.chat.npc_pilot_speech import (
    SPEECH_VARIANTS,
    render_pilot_speech,
)

from crimescene.chat.npc_history_display import (
    is_valid_stored_display,
    render_stored_npc_message,
)

from crimescene.chat.npc_natural_reply import LEGACY_HEADER

from crimescene.chat.npc_semantic_router import (
    SemanticRoute,
    build_semantic_social_reply,
)


def canonical(source, quote):
    return (
        LEGACY_HEADER
        + "\n"
        + f"“{quote}” (근거: {source})"
    )


@pytest.mark.parametrize(
    ("key", "speech"),
    list(SPEECH_VARIANTS.items()),
)
def test_exact_source_bound_speech(key, speech):
    npc, source, quote = key
    message = canonical(source, quote)

    assert render_pilot_speech(
        message, (source,), npc
    ) == speech

    assert is_valid_stored_display(
        message, (source,), npc, speech
    )

    assert render_stored_npc_message(
        message,
        (source,),
        character_id=npc,
        stored_display=speech,
    ) == speech


@pytest.mark.parametrize(
    ("key", "speech"),
    list(SPEECH_VARIANTS.items()),
)
def test_other_character_cannot_reuse_speech(key, speech):
    npc, source, quote = key

    other = "C02" if npc != "C02" else "C04"

    assert render_pilot_speech(
        canonical(source, quote),
        (source,),
        other,
    ) is None


@pytest.mark.parametrize(
    ("key", "speech"),
    list(SPEECH_VARIANTS.items()),
)
def test_modified_quote_is_rejected(key, speech):
    npc, source, quote = key

    message = canonical(
        source, quote + " 추가 정보"
    )

    assert render_pilot_speech(
        message, (source,), npc
    ) is None

    assert not is_valid_stored_display(
        message, (source,), npc, speech
    )


def test_source_mismatch_is_rejected():
    npc, source, quote = next(iter(SPEECH_VARIANTS))

    assert render_pilot_speech(
        canonical(source, quote),
        ("UNAUTHORIZED-SOURCE",),
        npc,
    ) is None


def test_fabricated_display_is_rejected():
    (npc, source, quote), speech = next(
        iter(SPEECH_VARIANTS.items())
    )

    assert not is_valid_stored_display(
        canonical(source, quote),
        (source,),
        npc,
        speech + " 사건 정답 추가",
    )


def test_partial_mapping_cannot_drop_unknown_quote():
    npc, source, quote = next(iter(SPEECH_VARIANTS))

    message = (
        canonical(source, quote)
        + '\n“별도의 승인 문장입니다.” (근거: OTHER)'
    )

    assert render_pilot_speech(
        message, (source, "OTHER"), npc
    ) is None


@pytest.mark.parametrize(
    "npc",
    [f"C{i:02d}" for i in range(1, 11)],
)
def test_personal_reply_distinct_from_check_in(npc):
    personal = build_semantic_social_reply(
        npc, SemanticRoute.PERSONAL
    )

    check_in = build_semantic_social_reply(
        npc, SemanticRoute.CHECK_IN
    )

    assert personal
    assert personal != check_in
