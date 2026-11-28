"""Semantic relevance and contextual repetition regression."""

import json

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from crimescene.chat import npc_relevance_guard as guard
from crimescene.chat import npc_chat_runtime as runtime
from crimescene.chat import npc_semantic_router as router

from crimescene.chat.npc_relevance_guard import (
    RelevanceDecision,
    judge_reply_relevance,
)

from crimescene.chat.npc_session import NPCSessionStore

from crimescene.retriever.npc_output_guard import (
    NPCGroundedReply,
)

from crimescene.retriever.npc_response_gate import (
    FALLBACK_REPLY,
)

from crimescene.scenario.schemas.game_state import GamePhase

from test_npc_conversation_memory import (
    exchange,
    make_context,
    SOURCE,
)

from test_npc_chat_runtime import (
    environment,
    valid_llm_output,
)


def make_reply():
    return NPCGroundedReply(
        text=exchange().npc_message,
        source_ids=(SOURCE,),
        grounded=True,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DIRECT", RelevanceDecision.DIRECT),
        ("PARTIAL", RelevanceDecision.PARTIAL),
        ("REJECT", RelevanceDecision.REJECT),
        ("", RelevanceDecision.REJECT),
        ("APPROVED", RelevanceDecision.REJECT),
        ("DIRECT\nextra", RelevanceDecision.REJECT),
    ],
)
def test_relevance_output_contract(
    monkeypatch,
    raw,
    expected,
):
    monkeypatch.setattr(
        guard,
        "generate_response",
        MagicMock(return_value=raw),
    )

    result = judge_reply_relevance(
        "피해자와 어떤 관계였나요?",
        make_reply(),
        [],
        context=make_context(),
        current_revision=2,
    )

    assert result is expected


def test_unapproved_source_never_reaches_judge(monkeypatch):
    generate = MagicMock(return_value="DIRECT")

    monkeypatch.setattr(
        guard,
        "generate_response",
        generate,
    )

    result = judge_reply_relevance(
        "어떤 관계인가요?",
        replace(
            make_reply(),
            source_ids=("PRIVATE-SOURCE",),
        ),
        [],
        context=make_context(),
        current_revision=2,
    )

    assert result is RelevanceDecision.REJECT
    generate.assert_not_called()


def test_revoked_history_not_sent_to_judge(monkeypatch):
    generate = MagicMock(return_value="DIRECT")

    monkeypatch.setattr(
        guard,
        "generate_response",
        generate,
    )

    result = judge_reply_relevance(
        "그 얘기를 다시 해주세요.",
        make_reply(),
        [
            exchange(
                quote="PRIVATE_HISTORY_SENTINEL",
                source="PRIVATE-SOURCE",
            ),
            exchange(revision=99),
        ],
        context=make_context(),
        current_revision=2,
    )

    assert result is RelevanceDecision.DIRECT

    payload = json.loads(
        generate.call_args.args[0]
    )

    assert len(payload["recent_turns"]) == 1

    assert "verified_reply" not in (
        payload["recent_turns"][0]
    )

    assert "PRIVATE_HISTORY_SENTINEL" not in (
        generate.call_args.args[0]
    )


@pytest.mark.parametrize(
    ("decision", "expected_grounded"),
    [
        (RelevanceDecision.DIRECT, True),
        (RelevanceDecision.PARTIAL, True),
        (RelevanceDecision.REJECT, False),
    ],
)
def test_semantic_runtime_paraphrase(
    monkeypatch,
    environment,
    decision,
    expected_grounded,
):
    monkeypatch.setenv(
        "CRIMESCENE_ENABLE_SEMANTIC_DIALOGUE",
        "true",
    )

    monkeypatch.setattr(
        router,
        "generate_response",
        MagicMock(return_value="IDENTITY"),
    )

    judge = MagicMock(
        side_effect=[
            RelevanceDecision.DIRECT,
            decision,
        ],
    )

    monkeypatch.setattr(
        runtime,
        "judge_reply_relevance",
        judge,
    )

    state, _, prepare = environment

    state = state.model_copy(
        update={
            "content_version": "case001_1120",
            "phase": GamePhase.INVESTIGATION,
        }
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    generate = MagicMock(
        return_value=valid_llm_output()
    )

    original_state = state.model_dump_json()

    def chat(question):
        prepare.return_value = replace(
            prepare.return_value,
            history=store.get_history(
                state, "C01"
            ),
        )

        return runtime.run_npc_chat(
            question,
            state=state,
            session_store=store,
            resources=None,
            generate=generate,
        )

    first = chat("무슨 일을 하시는 분이죠?")
    second = chat("직업이 어떻게 되세요?")

    assert first.reply.grounded
    assert second.reply.grounded is expected_grounded

    if expected_grounded:
        assert second.reply.source_ids == (
            first.reply.source_ids
        )
    else:
        assert second.reply.text == FALLBACK_REPLY
        assert second.reply.source_ids == ()

    assert judge.call_count == 2

    assert len(
        store.get_history(state, "C01")
    ) == 2

    assert state.model_dump_json() == original_state
