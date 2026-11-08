"""Issue #23 - NPCSessionStore와 SQLite 영구 저장소 통합 테스트."""

import pytest

from crimescene.chat.npc_session import NPCSessionStore
from crimescene.chat.npc_session_repository import (
    SQLiteNPCSessionRepository,
)
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.scenario.schemas.game_state import GameState


def make_state(
    session_id: str = "TEST-SESSION",
    *,
    unlocked: list[str] | None = None,
    revision: int = 0,
) -> GameState:
    return GameState(
        case_id="CASE-001",
        session_id=session_id,
        unlocked_characters=(["C01", "C02"] if unlocked is None else unlocked),
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
    text: str = "검증된 NPC 응답입니다.",
    source_id: str = "K-C01-01",
) -> NPCGroundedReply:
    return NPCGroundedReply(
        text=text,
        source_ids=(source_id,),
        grounded=True,
    )


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "npc_sessions.sqlite3"


def make_store(db_path):
    repository = SQLiteNPCSessionRepository(db_path)

    return NPCSessionStore(
        repository=repository,
    )


def test_persistent_npc_selection(db_path):
    state = make_state()

    store = make_store(db_path)

    store.select_npc(state, "C01")

    # 새로운 객체에서 선택 상태 복원
    restored = make_store(db_path)

    assert restored.get_active_npc(state) == "C01"


def test_persistent_history_after_restart(db_path):
    state = make_state()

    store = make_store(db_path)

    store.select_npc(state, "C01")

    store.append_verified_exchange(
        state,
        "C01",
        user_message="사건 당시 어디에 있었나요?",
        reply=make_reply(),
    )

    # 서버 재시작을 가정해 새로운 객체 생성
    restarted = make_store(db_path)

    history = restarted.get_history(state, "C01")

    assert len(history) == 1
    assert history[0].user_message == ("사건 당시 어디에 있었나요?")
    assert history[0].npc_message == ("검증된 NPC 응답입니다.")


def test_persistent_npc_switch(db_path):
    state = make_state()

    store = make_store(db_path)

    store.select_npc(state, "C01")

    store.append_verified_exchange(
        state,
        "C01",
        user_message="첫 번째 질문",
        reply=make_reply("C01 답변"),
    )

    store.select_npc(state, "C02")

    store.append_verified_exchange(
        state,
        "C02",
        user_message="두 번째 질문",
        reply=make_reply(
            "C02 답변",
            source_id="K-C02-01",
        ),
    )

    restarted = make_store(db_path)

    assert restarted.get_active_npc(state) == "C02"

    c01_history = restarted.get_history(state, "C01")
    c02_history = restarted.get_history(state, "C02")

    assert len(c01_history) == 1
    assert len(c02_history) == 1

    assert c01_history[0].npc_message == "C01 답변"
    assert c02_history[0].npc_message == "C02 답변"


def test_switch_back_restores_history(db_path):
    state = make_state()

    store = make_store(db_path)

    store.select_npc(state, "C01")

    store.append_verified_exchange(
        state,
        "C01",
        user_message="기억하나요?",
        reply=make_reply(),
    )

    store.select_npc(state, "C02")

    restored = store.select_npc(state, "C01")

    assert len(restored) == 1
    assert restored[0].user_message == "기억하나요?"


def test_different_game_sessions_isolated(db_path):
    store = make_store(db_path)

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

    restarted = make_store(db_path)

    assert len(restarted.get_history(state_a, "C01")) == 1
    assert restarted.get_history(state_b, "C01") == ()


def test_locked_npc_cannot_read_history(db_path):
    state = make_state()

    store = make_store(db_path)

    store.select_npc(state, "C02")

    locked_state = make_state(
        unlocked=["C01"],
        revision=1,
    )

    with pytest.raises(PermissionError):
        store.get_history(locked_state, "C02")

    assert store.get_active_npc(locked_state) is None


def test_unverified_reply_rejected(db_path):
    state = make_state()

    store = make_store(db_path)

    store.select_npc(state, "C01")

    invalid = NPCGroundedReply(
        text="LLM이 임의로 만든 응답",
        source_ids=(),
        grounded=False,
    )

    with pytest.raises(ValueError, match="검증되지 않은"):
        store.append_verified_exchange(
            state,
            "C01",
            user_message="질문",
            reply=invalid,
        )

    assert store.get_history(state, "C01") == ()


def test_fallback_reply_persisted(db_path):
    state = make_state()

    store = make_store(db_path)

    store.select_npc(state, "C01")

    fallback = NPCGroundedReply(
        text=FALLBACK_REPLY,
        source_ids=(),
        grounded=False,
    )

    store.append_verified_exchange(
        state,
        "C01",
        user_message="모르는 정보 질문",
        reply=fallback,
    )

    restarted = make_store(db_path)

    history = restarted.get_history(state, "C01")

    assert len(history) == 1
    assert history[0].npc_message == FALLBACK_REPLY


def test_old_revision_rejected(db_path):
    store = make_store(db_path)

    current = make_state(revision=5)
    old = make_state(revision=3)

    store.select_npc(current, "C01")

    restarted = make_store(db_path)

    with pytest.raises(ValueError, match="revision"):
        restarted.get_history(old, "C01")


def test_clear_persistent_session(db_path):
    state = make_state()

    store = make_store(db_path)

    store.select_npc(state, "C01")

    store.append_verified_exchange(
        state,
        "C01",
        user_message="삭제할 질문",
        reply=make_reply(),
    )

    store.clear_session(state)

    restarted = make_store(db_path)

    assert restarted.get_active_npc(state) is None
    assert restarted.get_history(state, "C01") == ()
