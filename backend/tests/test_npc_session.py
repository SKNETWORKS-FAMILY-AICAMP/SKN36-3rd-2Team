"""Issue #23 - NPC 대화 세션 관리 테스트."""

import pytest

from crimescene.chat.npc_session import NPCSessionStore
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.scenario.schemas.game_state import GameState


def make_state(
    session_id: str = "TEST-SESSION-001",
    *,
    unlocked: list[str] | None = None,
    revision: int = 0,
) -> GameState:
    return GameState(
        case_id="CASE-001",
        session_id=session_id,
        unlocked_characters=(["C01", "C02", "C03"] if unlocked is None else unlocked),
        evidence={},
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=revision,
        disclosed_cards=[],
        document_grants=[],
    )


def make_reply(
    text: str = "검증된 테스트 응답입니다.",
    *,
    source_id: str = "K-C01-01",
) -> NPCGroundedReply:
    return NPCGroundedReply(
        text=text,
        source_ids=(source_id,),
        grounded=True,
    )


def test_select_npc():
    store = NPCSessionStore()
    state = make_state()

    history = store.select_npc(state, "C01")

    assert history == ()
    assert store.get_active_npc(state) == "C01"


def test_switch_npc():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")
    store.select_npc(state, "C02")

    assert store.get_active_npc(state) == "C02"


def test_npc_history_is_independent():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    store.append_verified_exchange(
        state,
        "C01",
        user_message="첫 번째 인물에게 질문합니다.",
        reply=make_reply("C01의 검증된 답변"),
    )

    store.select_npc(state, "C02")

    assert store.get_history(state, "C02") == ()

    store.append_verified_exchange(
        state,
        "C02",
        user_message="두 번째 인물에게 질문합니다.",
        reply=make_reply(
            "C02의 검증된 답변",
            source_id="K-C02-01",
        ),
    )

    c01_history = store.get_history(state, "C01")
    c02_history = store.get_history(state, "C02")

    assert len(c01_history) == 1
    assert len(c02_history) == 1

    assert c01_history[0].npc_message == "C01의 검증된 답변"
    assert c02_history[0].npc_message == "C02의 검증된 답변"


def test_switch_back_restores_history():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    store.append_verified_exchange(
        state,
        "C01",
        user_message="기억하고 있나요?",
        reply=make_reply(),
    )

    store.select_npc(state, "C02")

    restored = store.select_npc(state, "C01")

    assert len(restored) == 1
    assert restored[0].user_message == "기억하고 있나요?"


def test_game_sessions_are_independent():
    store = NPCSessionStore()

    state_a = make_state("SESSION-A")
    state_b = make_state("SESSION-B")

    store.select_npc(state_a, "C01")
    store.select_npc(state_b, "C01")

    store.append_verified_exchange(
        state_a,
        "C01",
        user_message="세션 A의 질문",
        reply=make_reply(),
    )

    assert len(store.get_history(state_a, "C01")) == 1
    assert store.get_history(state_b, "C01") == ()


def test_locked_npc_rejected():
    store = NPCSessionStore()
    state = make_state(unlocked=["C01"])

    with pytest.raises(PermissionError):
        store.select_npc(state, "C02")

    assert store.get_active_npc(state) is None


def test_unknown_npc_rejected():
    store = NPCSessionStore()
    state = make_state()

    with pytest.raises(ValueError, match="NPC ID"):
        store.select_npc(state, "C11")


def test_inactive_npc_cannot_append():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    with pytest.raises(PermissionError):
        store.append_verified_exchange(
            state,
            "C02",
            user_message="다른 인물에게 질문",
            reply=make_reply(),
        )


def test_raw_llm_response_rejected():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    with pytest.raises(TypeError):
        store.append_verified_exchange(
            state,
            "C01",
            user_message="질문",
            reply="검증되지 않은 LLM 응답",
        )


def test_ungrounded_response_rejected():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    reply = NPCGroundedReply(
        text="근거 없는 임의 응답",
        source_ids=(),
        grounded=False,
    )

    with pytest.raises(ValueError, match="검증되지 않은"):
        store.append_verified_exchange(
            state,
            "C01",
            user_message="질문",
            reply=reply,
        )


def test_fallback_reply_allowed():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    fallback = NPCGroundedReply(
        text=FALLBACK_REPLY,
        source_ids=(),
        grounded=False,
    )

    result = store.append_verified_exchange(
        state,
        "C01",
        user_message="모르는 정보에 관한 질문",
        reply=fallback,
    )

    assert result.npc_message == FALLBACK_REPLY
    assert result.source_ids == ()


def test_grounded_reply_requires_source():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    invalid_reply = NPCGroundedReply(
        text="출처가 없는 응답",
        source_ids=(),
        grounded=True,
    )

    with pytest.raises(ValueError, match="출처"):
        store.append_verified_exchange(
            state,
            "C01",
            user_message="질문",
            reply=invalid_reply,
        )


def test_history_limit():
    store = NPCSessionStore(
        max_exchanges_per_npc=2,
    )
    state = make_state()

    store.select_npc(state, "C01")

    for index in range(3):
        store.append_verified_exchange(
            state,
            "C01",
            user_message=f"질문 {index}",
            reply=make_reply(f"답변 {index}"),
        )

    history = store.get_history(state, "C01")

    assert len(history) == 2
    assert history[0].user_message == "질문 1"
    assert history[1].user_message == "질문 2"


def test_old_revision_rejected():
    store = NPCSessionStore()

    current = make_state(revision=5)
    old = make_state(revision=3)

    store.select_npc(current, "C01")

    with pytest.raises(ValueError, match="revision"):
        store.get_history(old, "C01")


def test_clear_session():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    store.append_verified_exchange(
        state,
        "C01",
        user_message="테스트 질문",
        reply=make_reply(),
    )

    store.clear_session(state)

    assert store.get_active_npc(state) is None
    assert store.get_history(state, "C01") == ()


def test_session_limit():
    store = NPCSessionStore(max_sessions=1)

    store.select_npc(make_state("SESSION-A"), "C01")

    with pytest.raises(RuntimeError, match="세션 수"):
        store.select_npc(make_state("SESSION-B"), "C01")


def test_invalid_message_rejected():
    store = NPCSessionStore()
    state = make_state()

    store.select_npc(state, "C01")

    with pytest.raises(ValueError, match="비어"):
        store.append_verified_exchange(
            state,
            "C01",
            user_message="   ",
            reply=make_reply(),
        )
