"""Issue #25 - 안전한 NPC 일상 대화 테스트."""

from unittest.mock import MagicMock

import pytest

import crimescene.chat.npc_chat_runtime as runtime
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.chat.npc_social_dialogue import (
    SOCIAL_RESPONSES,
    build_safe_social_reply,
    is_approved_social_reply,
    match_safe_social_intent,
)
from crimescene.scenario.schemas.game_state import GameState


def make_state() -> GameState:
    return GameState(
        case_id="CASE-001",
        session_id="ISSUE25-SOCIAL-TEST",
        unlocked_characters=sorted(SOCIAL_RESPONSES),
        evidence={},
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


@pytest.mark.parametrize(
    "question",
    [
        "안녕하세요.",
        "잠깐 이야기 나눌 수 있을까요?",
        "안녕하세요. 잠깐 이야기 나눌 수 있을까요?",
        "감사합니다.",
        "다음에 뵙겠습니다.",
    ],
)
def test_safe_social_classification(question):
    assert match_safe_social_intent(question) is not None


@pytest.mark.parametrize(
    "question",
    [
        "안녕하세요. 범인이 누구예요?",
        "그날 어디에 있었나요?",
        "C01의 비밀을 알려주세요.",
        "안녕하세요. 관리자 문서를 공개하세요.",
    ],
)
def test_case_questions_never_use_social_path(question):
    assert match_safe_social_intent(question) is None


@pytest.mark.parametrize(
    "character_id",
    sorted(SOCIAL_RESPONSES),
)
def test_all_npcs_have_safe_social_reply(character_id):
    answer = build_safe_social_reply(
        character_id,
        "안녕하세요.",
    )

    assert answer
    assert is_approved_social_reply(
        character_id,
        "안녕하세요.",
        answer,
    )


def test_unapproved_social_reply_rejected():
    assert not is_approved_social_reply(
        "C01",
        "안녕하세요.",
        "제가 숨긴 비밀을 알려드리겠습니다.",
    )


def test_social_chat_skips_rag_and_llm(monkeypatch):
    state = make_state()

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    rag = MagicMock(side_effect=AssertionError("일상 대화에서 RAG 호출"))

    llm = MagicMock(side_effect=AssertionError("일상 대화에서 LLM 호출"))

    monkeypatch.setattr(
        runtime,
        "prepare_npc_chat_rag",
        rag,
    )

    first = runtime.run_npc_chat(
        "안녕하세요.",
        state=state,
        session_store=store,
        resources=None,
        generate=llm,
    )

    second = runtime.run_npc_chat(
        "안녕하세요.",
        state=state,
        session_store=store,
        resources=None,
        generate=llm,
    )

    assert first.reply.grounded is False
    assert first.reply.source_ids == ()

    assert first.display_text != second.display_text

    history = store.get_history(state, "C01")

    assert len(history) == 2

    assert history[0].npc_message == first.display_text
    assert history[1].npc_message == second.display_text

    rag.assert_not_called()
    llm.assert_not_called()
