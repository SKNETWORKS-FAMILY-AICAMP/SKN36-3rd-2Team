"""Issue #23 - NPC RAG, LLM 검증 및 대화 저장 통합 테스트."""

import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

import crimescene.chat.npc_chat_runtime as module
from crimescene.chat.npc_rag_service import NPCChatRAGResult
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.chat.npc_session_repository import (
    SQLiteNPCSessionRepository,
)
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
    AuthorizedMultisourceItem,
)
from crimescene.retriever.npc_response_gate import (
    FALLBACK_REPLY,
    NPCReplyPlan,
)
from crimescene.scenario.schemas.game_state import GameState

QUESTION = "그날 어디에 있었나요?"
QUOTE = "그날 저는 복도에서 장부를 보았습니다."
SOURCE_ID = "K-C01-TEST"


def make_state():
    return GameState(
        case_id="CASE-001",
        session_id="NPC-RUNTIME-TEST",
        unlocked_characters=["C01", "C02"],
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
        text=f"[SOURCE 1]\n{QUOTE}\n[/SOURCE]",
    )


def make_plan():
    context = make_context()

    return NPCReplyPlan(
        can_call_llm=True,
        fallback_reply=None,
        messages=(
            {
                "role": "system",
                "content": "당신은 윤태식입니다.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "player_question": QUESTION,
                        "verified_context": context.text,
                    },
                    ensure_ascii=False,
                ),
            },
        ),
        source_ids=(SOURCE_ID,),
        authorized_context=context,
    )


def make_blocked_plan():
    return NPCReplyPlan(
        can_call_llm=False,
        fallback_reply=FALLBACK_REPLY,
        messages=(),
        source_ids=(),
    )


def valid_llm_output():
    return json.dumps(
        {
            "quotes": [
                {
                    "source_id": SOURCE_ID,
                    "quote": QUOTE,
                }
            ]
        },
        ensure_ascii=False,
    )


@pytest.fixture
def environment(monkeypatch):
    state = make_state()
    store = NPCSessionStore()
    store.select_npc(state, "C01")

    prepare_mock = MagicMock(
        return_value=NPCChatRAGResult(
            character_id="C01",
            history=(),
            reply_plan=make_plan(),
        )
    )

    monkeypatch.setattr(
        module,
        "prepare_npc_chat_rag",
        prepare_mock,
    )

    return state, store, prepare_mock


def test_verified_reply_saved(environment):
    state, store, _ = environment

    generate = MagicMock(return_value=valid_llm_output())

    result = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert result.character_id == "C01"
    assert result.reply.grounded is True
    assert result.reply.source_ids == (SOURCE_ID,)

    history = store.get_history(state, "C01")

    assert len(history) == 1
    assert QUOTE in history[0].npc_message
    assert history[0].source_ids == (SOURCE_ID,)

    generate.assert_called_once()

    assert result.display_text == QUOTE
    assert result.reply.source_ids == (SOURCE_ID,)
    assert "(근거:" not in result.display_text

    # 저장된 원본은 기존 검증 형식을 유지합니다.
    assert "근거:" in result.exchange.npc_message


def test_unverified_quote_returns_fallback(environment):
    state, store, _ = environment

    invalid_output = json.dumps(
        {
            "quotes": [
                {
                    "source_id": SOURCE_ID,
                    "quote": "승인되지 않은 새로운 사건 정보",
                }
            ]
        },
        ensure_ascii=False,
    )

    result = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=lambda messages: invalid_output,
    )

    assert result.reply.grounded is False
    assert result.reply.text == FALLBACK_REPLY

    history = store.get_history(state, "C01")

    assert len(history) == 1
    assert history[0].npc_message == FALLBACK_REPLY
    assert history[0].source_ids == ()


def test_no_evidence_skips_llm(environment):
    state, store, prepare_mock = environment

    prepare_mock.return_value = NPCChatRAGResult(
        character_id="C01",
        history=(),
        reply_plan=make_blocked_plan(),
    )

    generate = MagicMock()

    result = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert result.reply.text == FALLBACK_REPLY
    assert result.reply.grounded is False

    generate.assert_not_called()
    assert len(store.get_history(state, "C01")) == 1


def test_missing_authorized_context_blocks_llm(environment):
    state, store, prepare_mock = environment

    prepare_mock.return_value = NPCChatRAGResult(
        character_id="C01",
        history=(),
        reply_plan=replace(
            make_plan(),
            authorized_context=None,
        ),
    )

    generate = MagicMock()

    with pytest.raises(RuntimeError, match="컨텍스트"):
        module.run_npc_chat(
            QUESTION,
            state=state,
            session_store=store,
            resources=None,
            generate=generate,
        )

    generate.assert_not_called()
    assert store.get_history(state, "C01") == ()


def test_npc_switch_during_generation_blocks_save(environment):
    state, store, _ = environment

    def generate_and_switch(messages):
        store.select_npc(state, "C02")
        return valid_llm_output()

    with pytest.raises(RuntimeError, match="NPC가 변경"):
        module.run_npc_chat(
            QUESTION,
            state=state,
            session_store=store,
            resources=None,
            generate=generate_and_switch,
        )

    assert store.get_history(state, "C01") == ()
    assert store.get_history(state, "C02") == ()


def test_llm_exception_does_not_save(environment):
    state, store, _ = environment

    def failing_llm(messages):
        raise RuntimeError("Ollama 연결 실패")

    with pytest.raises(RuntimeError, match="Ollama"):
        module.run_npc_chat(
            QUESTION,
            state=state,
            session_store=store,
            resources=None,
            generate=failing_llm,
        )

    assert store.get_history(state, "C01") == ()


def test_game_revision_change_blocks_save(environment):
    state, store, _ = environment

    def generate_and_change_state(messages):
        state.revision += 1
        return valid_llm_output()

    with pytest.raises(RuntimeError, match="GameState"):
        module.run_npc_chat(
            QUESTION,
            state=state,
            session_store=store,
            resources=None,
            generate=generate_and_change_state,
        )

    assert store.get_history(state, "C01") == ()


def test_persist_verified_reply_after_restart(
    environment,
    tmp_path,
):
    state, _, prepare_mock = environment

    db_path = tmp_path / "npc_runtime.sqlite3"

    repository = SQLiteNPCSessionRepository(db_path)
    store = NPCSessionStore(repository=repository)

    store.select_npc(state, "C01")

    module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=lambda messages: valid_llm_output(),
    )

    restarted = NPCSessionStore(
        repository=SQLiteNPCSessionRepository(db_path),
    )

    history = restarted.get_history(state, "C01")

    assert len(history) == 1
    assert QUOTE in history[0].npc_message
    assert history[0].source_ids == (SOURCE_ID,)

    prepare_mock.assert_called_once()


def test_different_question_does_not_repeat_same_reply(environment):
    state, store, prepare_mock = environment
    generate = lambda messages: valid_llm_output()

    first = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert first.reply.grounded is True

    # 같은 NPC의 이전 대화 기록을 다음 요청에 전달합니다.
    prepare_mock.return_value = NPCChatRAGResult(
        character_id="C01",
        history=store.get_history(state, "C01"),
        reply_plan=make_plan(),
    )

    second = module.run_npc_chat(
        "그 기록의 정확한 시각은 언제입니까?",
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert second.reply.grounded is False
    assert second.display_text == FALLBACK_REPLY
    assert second.reply.source_ids == ()

    history = store.get_history(state, "C01")
    assert len(history) == 2
    assert history[-1].npc_message == FALLBACK_REPLY
