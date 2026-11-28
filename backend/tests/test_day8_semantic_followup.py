"""Semantic follow-up grounding regression."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from crimescene.chat import npc_relevance_guard as guard

from crimescene.chat.npc_semantic_router import (
    SemanticRoute,
    resolve_semantic_followup,
)

from crimescene.chat.npc_relevance_guard import (
    RelevanceDecision,
    judge_reply_relevance,
)

from test_npc_conversation_memory import (
    exchange,
    fallback_exchange,
    make_context,
)

from test_day8_relevance_guard import make_reply


def test_elaboration_without_history():
    assert resolve_semantic_followup(
        SemanticRoute.ELABORATE,
        [],
        current_revision=2,
    ) is SemanticRoute.CLARIFY


def test_elaboration_after_refusal():
    assert resolve_semantic_followup(
        SemanticRoute.ELABORATE,
        [fallback_exchange()],
        current_revision=2,
    ) is SemanticRoute.CLARIFY


def test_elaboration_after_grounded_answer():
    assert resolve_semantic_followup(
        SemanticRoute.ELABORATE,
        [exchange()],
        current_revision=2,
    ) is SemanticRoute.ELABORATE


def test_elaboration_future_revision():
    assert resolve_semantic_followup(
        SemanticRoute.ELABORATE,
        [exchange(revision=99)],
        current_revision=2,
    ) is SemanticRoute.CLARIFY


def test_specific_followup_after_refusal():
    assert resolve_semantic_followup(
        SemanticRoute.FOLLOW_UP,
        [fallback_exchange()],
        current_revision=2,
    ) is SemanticRoute.FOLLOW_UP


@pytest.mark.parametrize(
    "history",
    [
        [],
        [fallback_exchange()],
        [exchange(revision=99)],
        [
            replace(
                exchange(),
                source_ids=("REVOKED-SOURCE",),
            )
        ],
    ],
)
def test_unverified_elaboration_blocked_before_llm(
    monkeypatch,
    history,
):
    generate = MagicMock(return_value="DIRECT")

    monkeypatch.setattr(
        guard,
        "generate_response",
        generate,
    )

    decision = judge_reply_relevance(
        "그 얘기 좀 더 해주세요.",
        make_reply(),
        history,
        context=make_context(),
        current_revision=2,
        require_previous_grounded=True,
    )

    assert decision is RelevanceDecision.REJECT
    generate.assert_not_called()
