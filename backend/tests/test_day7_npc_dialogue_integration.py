
"""Issue #176 - integrated NPC conversation regression.

Python 3.13 / pytest 9
Synthetic authorized context; real dialogue runtime and SQLite.
"""

import json
from unittest.mock import MagicMock

import pytest

from crimescene.chat import npc_chat_runtime as runtime
from crimescene.chat.npc_dynamic_persona import (
    build_dynamic_npc_persona,
)
from crimescene.chat.npc_emotional_state import (
    NPCMood,
    derive_npc_emotional_state,
)
from crimescene.chat.npc_history_display import (
    render_stored_npc_message,
)
from crimescene.chat.npc_memory_recall import (
    NO_HISTORY_REPLY,
)
from crimescene.chat.npc_pressure_dialogue import (
    is_approved_pressure_reply,
)
from crimescene.chat.npc_rag_service import (
    NPCChatRAGResult,
)
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.chat.npc_session_repository import (
    SQLiteNPCSessionRepository,
)
from crimescene.chat.npc_social_dialogue import (
    build_safe_social_reply,
)
from crimescene.chat.npc_social_style import SOCIAL_STYLES
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
    AuthorizedMultisourceItem,
)
from crimescene.retriever.npc_response_gate import (
    FALLBACK_REPLY,
    NPCReplyPlan,
)
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)


NPC_IDS = tuple(f"C{i:02d}" for i in range(1, 11))

GREETING = "안녕하세요."
IDENTITY = "본인에 대해서 간단하게 소개해 주세요."
FOLLOW_UP = "방금 말씀하신 내용을 좀 더 자세히 설명해 주세요."
RECALL = "제가 아까 어떤 질문을 했는지 기억하세요?"
PRESSURE = "거짓말하거나 숨기고 있는 내용이 있습니까?"


def make_state(session_id="INTEGRATION-176"):
    return GameState(
        case_id="CASE-001",
        session_id=session_id,
        content_version="case001_1120",
        phase=GamePhase.INVESTIGATION,
        current_chapter="CH01",
        unlocked_chapters=["CH00", "CH01"],
        unlocked_characters=list(NPC_IDS),
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


def make_store(path):
    return NPCSessionStore(
        repository=SQLiteNPCSessionRepository(path)
    )


def make_context(npc):
    source_id = f"K-{npc}-TEST"

    first_quote = (
        f"{npc} identity information for integration testing."
    )

    second_quote = (
        f"{npc} additional verified information for testing."
    )

    content = f"{first_quote} {second_quote}"

    item = AuthorizedMultisourceItem(
        kind="chunk",
        item_id=f"TEST-{npc}",
        source_id=source_id,
        score=0.1,
        methods=("dense",),
        content=content,
        truth_status="character_claim",
    )

    context = AuthorizedMultisourceContext(
        items=(item,),
        text=f"[SOURCE 1]\n{content}\n[/SOURCE]",
    )

    return context, source_id, first_quote, second_quote


def make_output(source_id, quote):
    return json.dumps({
        "quotes": [{
            "source_id": source_id,
            "quote": quote,
        }],
    })


def make_plan(query, npc, context, source_id):
    return NPCReplyPlan(
        can_call_llm=True,
        fallback_reply=None,
        messages=(
            {
                "role": "system",
                "content": f"Authorized test NPC: {npc}",
            },
            {
                "role": "user",
                "content": json.dumps({
                    "player_question": query,
                    "verified_context": context.text,
                }, ensure_ascii=False),
            },
        ),
        source_ids=(source_id,),
        authorized_context=context,
    )


def assert_source_free(turn):
    assert not turn.reply.grounded
    assert turn.reply.source_ids == ()
    assert turn.reply.text != FALLBACK_REPLY
    assert turn.display_text == turn.reply.text


def assert_grounded(turn, source_id, quote):
    assert turn.reply.grounded
    assert turn.reply.source_ids == (source_id,)
    assert quote in turn.display_text
    assert source_id not in turn.display_text
    assert turn.exchange.npc_message == turn.reply.text
    assert turn.exchange.display_text == turn.display_text


@pytest.mark.parametrize("npc", NPC_IDS)
def test_full_npc_conversation_lifecycle(
    npc,
    tmp_path,
    monkeypatch,
):
    state = make_state()
    original_state = state.model_dump()

    db_path = tmp_path / "npc-integration.sqlite3"

    store = make_store(db_path)
    store.select_npc(state, npc)

    context, source_id, first_quote, second_quote = (
        make_context(npc)
    )

    def prepare(
        query,
        *,
        state,
        session_store,
        **kwargs,
    ):
        active = session_store.get_active_npc(state)

        assert active == npc

        return NPCChatRAGResult(
            character_id=active,
            history=session_store.get_history(
                state,
                active,
            ),
            reply_plan=make_plan(
                query,
                active,
                context,
                source_id,
            ),
        )

    prepare_mock = MagicMock(side_effect=prepare)

    monkeypatch.setattr(
        runtime,
        "prepare_npc_chat_rag",
        prepare_mock,
    )

    generate = MagicMock(side_effect=[
        make_output(source_id, first_quote),
        make_output(source_id, second_quote),
    ])

    def chat(question, *, active_store=None, game=None):
        return runtime.run_npc_chat(
            question,
            state=game if game is not None else state,
            session_store=(
                active_store
                if active_store is not None
                else store
            ),
            resources=None,
            generate=generate,
        )

    # 1. NPC-specific greeting.

    greeting = chat(GREETING)

    assert_source_free(greeting)

    assert greeting.reply.text == build_safe_social_reply(
        npc,
        GREETING,
    )

    generate.assert_not_called()

    # 2. Grounded identity and dynamic persona.

    identity = chat(IDENTITY)

    assert_grounded(
        identity,
        source_id,
        first_quote,
    )

    messages = generate.call_args.args[0]
    system = messages[0]["content"]

    persona = build_dynamic_npc_persona(
        state=state,
        character_id=npc,
    )

    assert persona.speaking_style == (
        SOCIAL_STYLES[npc].speaking_style
    )

    assert persona.chapter == "CH01"
    assert persona.stage == 1

    assert "[DYNAMIC NPC PERSONA]" in system
    assert persona.speaking_style in system
    assert "[NPC DIALOGUE INTENT]" in system
    assert "[NPC EMOTIONAL STATE]" in system

    assert generate.call_count == 1

    # 3. Repeated question must revalidate stored quotes.

    repeated = chat(IDENTITY)

    assert_grounded(
        repeated,
        source_id,
        first_quote,
    )

    assert repeated.reply == identity.reply
    assert generate.call_count == 1
    assert prepare_mock.call_count == 2

    # 4. Follow-up with distinct verified evidence.

    follow_up = chat(FOLLOW_UP)

    assert_grounded(
        follow_up,
        source_id,
        second_quote,
    )

    assert generate.call_count == 2

    messages = generate.call_args.args[0]
    payload = json.loads(messages[1]["content"])

    assert payload["player_question"] == FOLLOW_UP
    assert payload["conversation_history"]

    assert any(
        item["player_question"] == IDENTITY
        and first_quote in item.get("npc_reply", "")
        for item in payload["conversation_history"]
    )

    # 5. Safe recall of the preceding follow-up.

    recalled = chat(RECALL)

    assert_source_free(recalled)

    assert recalled.reply.text != NO_HISTORY_REPLY
    assert generate.call_count == 2

    # 6. Four pressure turns.

    pressure_turns = []

    for _ in range(4):
        turn = chat(PRESSURE)

        assert_source_free(turn)

        assert is_approved_pressure_reply(
            npc,
            PRESSURE,
            turn.reply.text,
            state=state,
        )

        pressure_turns.append(turn)

    assert (
        pressure_turns[0].reply.text
        != pressure_turns[-1].reply.text
    )

    assert generate.call_count == 2
    assert prepare_mock.call_count == 3

    history = store.get_history(state, npc)

    assert len(history) == 9

    emotion = derive_npc_emotional_state(
        "현재 상태를 확인하겠습니다.",
        state=state,
        character_id=npc,
        history=history,
    )

    assert emotion.mood == NPCMood.TENSE

    # 7. Reopen SQLite and restore canonical/display replies.

    restored_store = make_store(db_path)

    assert restored_store.get_active_npc(state) == npc

    restored = restored_store.get_history(
        state,
        npc,
    )

    assert restored == history

    all_turns = [
        greeting,
        identity,
        repeated,
        follow_up,
        recalled,
        *pressure_turns,
    ]

    for exchange, turn in zip(
        restored,
        all_turns,
        strict=True,
    ):
        display = render_stored_npc_message(
            exchange.npc_message,
            exchange.source_ids,
            character_id=npc,
            stored_display=exchange.display_text,
        )

        assert display == turn.display_text

    # 8. Another NPC must not inherit the previous history.

    other_npc = next(
        item for item in NPC_IDS
        if item != npc
    )

    restored_store.select_npc(state, other_npc)

    assert restored_store.get_history(
        state,
        other_npc,
    ) == ()

    other_recall = chat(
        RECALL,
        active_store=restored_store,
    )

    assert other_recall.reply.text == NO_HISTORY_REPLY
    assert other_recall.reply.source_ids == ()

    restored_store.select_npc(state, npc)

    assert restored_store.get_history(
        state,
        npc,
    ) == history

    # 9. A second session using the same NPC stays isolated.

    another_game = make_state(
        session_id="INTEGRATION-176-SECOND"
    )

    restored_store.select_npc(
        another_game,
        npc,
    )

    assert restored_store.get_history(
        another_game,
        npc,
    ) == ()

    isolated_recall = chat(
        RECALL,
        active_store=restored_store,
        game=another_game,
    )

    assert isolated_recall.reply.text == NO_HISTORY_REPLY
    assert isolated_recall.reply.source_ids == ()

    assert restored_store.get_history(
        state,
        npc,
    ) == history

    # 10. Dialogue must not mutate game state.

    assert state.model_dump() == original_state
    assert generate.call_count == 2
    assert prepare_mock.call_count == 3
