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
    assert result.display_text == FALLBACK_REPLY
    assert "다른 단서를 확인하신 뒤" in result.display_text
    assert result.exchange.npc_message == FALLBACK_REPLY
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


# Issue #171 - expanded persona and retry integration


def test_expanded_runtime_uses_persona_and_intent(environment):
    state, _, prepare_mock = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    generate = MagicMock(
        return_value=valid_llm_output()
    )

    turn = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert turn.reply.grounded is True
    assert turn.reply.source_ids == (SOURCE_ID,)
    assert QUOTE in turn.display_text
    assert turn.display_text.startswith(
        "이 부분부터 말씀드리겠습니다."
    )

    history = store.get_history(state, "C01")

    assert history[-1].npc_message == turn.reply.text
    assert history[-1].npc_message != turn.display_text

    messages = generate.call_args.args[0]
    system_prompt = messages[0]["content"]

    assert "[DYNAMIC NPC PERSONA]" in system_prompt
    assert "[NPC DIALOGUE INTENT]" in system_prompt

    generate.assert_called_once()
    prepare_mock.assert_called_once()


def test_expanded_runtime_skips_explicit_empty_retry(environment):
    state, _, _ = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    generate = MagicMock(
        side_effect=[
            '{"quotes": []}',
            valid_llm_output(),
        ]
    )

    turn = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert turn.reply.grounded is False
    assert turn.reply.source_ids == ()
    assert turn.display_text == FALLBACK_REPLY

    generate.assert_called_once()


def test_legacy_runtime_still_retries_empty_quotes(environment):
    state, store, _ = environment

    generate = MagicMock(
        side_effect=[
            '{"quotes": []}',
            valid_llm_output(),
        ]
    )

    turn = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert turn.reply.grounded is True
    assert generate.call_count == 2
    assert turn.display_text == QUOTE


def test_expanded_invalid_json_still_retries(environment):
    state, _, _ = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    generate = MagicMock(
        side_effect=[
            "INVALID JSON",
            valid_llm_output(),
        ]
    )

    turn = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert turn.reply.grounded is True
    assert generate.call_count == 2


def test_expanded_unapproved_source_still_blocked(environment):
    state, _, _ = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    generate = MagicMock(
        return_value=json.dumps({
            "quotes": [
                {
                    "source_id": "ADMIN-SECRET",
                    "quote": "PRIVATE_SECRET_SENTINEL",
                }
            ]
        })
    )

    turn = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert turn.reply.grounded is False
    assert turn.reply.source_ids == ()
    assert turn.display_text == FALLBACK_REPLY
    assert "PRIVATE_SECRET_SENTINEL" not in turn.display_text

    assert generate.call_count == 2


# Issue #172 - repeat memory integration


def test_expanded_repeat_reuses_verified_memory(environment):
    from dataclasses import replace

    state, _, prepare_mock = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    generate = MagicMock(return_value=valid_llm_output())

    first = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    prepare_mock.return_value = replace(
        prepare_mock.return_value,
        history=store.get_history(state, "C01"),
    )

    second = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert first.reply.grounded
    assert second.reply.grounded
    assert first.reply == second.reply

    # Second turn reuses verified memory, not the model.
    assert generate.call_count == 1
    assert prepare_mock.call_count == 2

    assert prepare_mock.call_args.kwargs[
        "use_memory_context"
    ] is True

    assert len(store.get_history(state, "C01")) == 2


def test_expanded_evidence_turn_does_not_replay_memory(environment):
    from dataclasses import replace

    state, _, prepare_mock = environment

    state = type(state).model_validate({
        **state.model_dump(),
        "content_version": "case001_1120",
        "evidence": {
            "E01": {"stage": "found"},
        },
        "presented": {'C01': ['E01']},
    })

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    generate = MagicMock(return_value=valid_llm_output())

    module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    prepare_mock.return_value = replace(
        prepare_mock.return_value,
        history=store.get_history(state, "C01"),
    )

    turn = module.run_npc_chat(
        QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
        evidence_just_presented=True,
    )

    assert turn.reply.grounded
    assert generate.call_count == 2

    assert not prepare_mock.call_args.kwargs.get(
        "use_memory_context", False
    )


# Issue #172 - safe recall runtime integration

MEMORY_RECALL_QUESTION = (
    "제가 아까 어떤 질문을 했는지 기억하세요?"
)

MEMORY_PREVIOUS_QUESTION = (
    "방금 말씀하신 내용을 좀 더 자세히 설명해 주세요."
)


def test_expanded_memory_recall_without_llm(environment):
    state, _, prepare_mock = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    store.append_verified_exchange(
        state,
        "C01",
        user_message=MEMORY_PREVIOUS_QUESTION,
        reply=module.NPCGroundedReply(
            text=module.FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        ),
    )

    generate = MagicMock(
        side_effect=AssertionError("Unexpected LLM call")
    )

    turn = module.run_npc_chat(
        MEMORY_RECALL_QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert "직전 답변을 더 설명해 달라고" in turn.reply.text
    assert not turn.reply.grounded
    assert not turn.reply.source_ids
    assert turn.display_text == turn.exchange.npc_message

    generate.assert_not_called()
    prepare_mock.assert_not_called()

    assert len(store.get_history(state, "C01")) == 2


def test_expanded_memory_recall_without_history(environment):
    state, _, prepare_mock = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    generate = MagicMock(
        side_effect=AssertionError("Unexpected LLM call")
    )

    turn = module.run_npc_chat(
        MEMORY_RECALL_QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert turn.reply.text == "아직 저와 나눈 대화가 없습니다."
    assert len(store.get_history(state, "C01")) == 1

    generate.assert_not_called()
    prepare_mock.assert_not_called()


def test_session_rejects_fabricated_memory_reply(environment):
    state, _, _ = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    # A valid server phrase is still invalid without matching history.
    forged = module.NPCGroundedReply(
        text="네. 직전 답변을 더 설명해 달라고 하셨습니다.",
        source_ids=(),
        grounded=False,
    )

    with pytest.raises(ValueError):
        store.append_verified_exchange(
            state,
            "C01",
            user_message=MEMORY_RECALL_QUESTION,
            reply=forged,
        )

    assert store.get_history(state, "C01") == ()


def test_legacy_memory_recall_preserves_rag_path(environment):
    state, store, prepare_mock = environment

    generate = MagicMock(return_value=valid_llm_output())

    module.run_npc_chat(
        MEMORY_RECALL_QUESTION,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    prepare_mock.assert_called_once()

# ============================================================
# Issue #173 - emotional runtime integration
# ============================================================

EMOTION_PRESSURE = "거짓말하고 계신 거 아닌가요?"


def prepare_emotional_runtime(environment, monkeypatch):
    from dataclasses import replace

    state, _, _ = environment

    state = state.model_copy(
        update={"content_version": "case001_1120"}
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    for _ in range(3):
        store.append_verified_exchange(
            state,
            "C01",
            user_message=EMOTION_PRESSURE,
            reply=module.NPCGroundedReply(
                text=module.FALLBACK_REPLY,
                source_ids=(),
                grounded=False,
            ),
        )

    original_prepare = module.prepare_npc_chat_rag

    def prepare(*args, **kwargs):
        result = original_prepare(*args, **kwargs)

        return replace(
            result,
            history=store.get_history(
                state,
                result.character_id,
            ),
        )

    monkeypatch.setattr(
        module,
        "prepare_npc_chat_rag",
        prepare,
    )

    return state, store


def test_emotion_runtime_applies_tense_opener(
    environment,
    monkeypatch,
):
    state, store = prepare_emotional_runtime(
        environment,
        monkeypatch,
    )

    before = state.model_dump()

    generate = MagicMock(
        return_value=valid_llm_output()
    )

    turn = module.run_npc_chat(
        EMOTION_PRESSURE,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert turn.reply.grounded

    assert turn.display_text.startswith(
        "잠시만요. 핵심만 말씀드리겠습니다.\n"
    )

    assert turn.exchange.display_text == turn.display_text
    assert turn.exchange.npc_message == turn.reply.text
    assert state.model_dump() == before

    generate.assert_called_once()

    messages = generate.call_args.args[0]

    assert "[NPC EMOTIONAL STATE]" in messages[0]["content"]
    assert "짧고 통제된 표현" in messages[0]["content"]


def test_emotion_runtime_keeps_fallback(
    environment,
    monkeypatch,
):
    state, store = prepare_emotional_runtime(
        environment,
        monkeypatch,
    )

    generate = MagicMock(
        return_value='{"quotes": []}'
    )

    turn = module.run_npc_chat(
        EMOTION_PRESSURE,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert turn.reply.text == module.FALLBACK_REPLY
    assert turn.display_text == module.FALLBACK_REPLY
    assert not turn.reply.grounded
    assert turn.reply.source_ids == ()

    assert turn.exchange.display_text is None

    generate.assert_called_once()


def test_emotion_runtime_does_not_leak_attack_into_prompt(
    environment,
    monkeypatch,
):
    state, store = prepare_emotional_runtime(
        environment,
        monkeypatch,
    )

    sentinel = "PRIVATE_EMOTION_ATTACK_173"

    generate = MagicMock(
        return_value='{"quotes": []}'
    )

    turn = module.run_npc_chat(
        EMOTION_PRESSURE + " " + sentinel,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    messages = generate.call_args.args[0]

    assert sentinel not in messages[0]["content"]
    assert turn.reply.text == module.FALLBACK_REPLY


def test_legacy_runtime_has_no_emotional_prompt(environment):
    state, store, _ = environment

    generate = MagicMock(
        return_value=valid_llm_output()
    )

    module.run_npc_chat(
        EMOTION_PRESSURE,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    messages = generate.call_args.args[0]

    assert "[NPC EMOTIONAL STATE]" not in messages[0]["content"]
