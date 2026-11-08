"""Issue #25 - 안전한 일상 응답의 SQLite 원자적 저장 회귀 테스트.

기존 test_atomic_dialogue.py를 교체하지 않고 독립 실행합니다.
"""

import pytest

from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_session import NPCExchange
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def database(tmp_path):
    """테스트 전용 SQLite에 NPC 세션과 초기 GameState를 등록합니다."""
    path = tmp_path / "issue25_atomic_social.sqlite3"
    repo = SQLiteCase001Repository(path)
    state = GameState(
        case_id="CASE-001",
        session_id="ISSUE25-SOCIAL-ATOMIC",
        unlocked_characters=["C01"],
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
    repo.save_selection(state.session_id, "C01", state.revision)
    repo.register_state(state)
    return repo, state, path


def test_safe_social_reply_atomic_commit(database):
    """안전한 일상 대화를 원자적으로 저장할 수 있어야 한다."""

    from crimescene.chat.npc_social_dialogue import build_safe_social_reply

    repo, state, path = database

    question = "안녕하세요."

    answer = build_safe_social_reply(
        "C01",
        question,
    )

    reply = NPCGroundedReply(
        text=answer,
        source_ids=(),
        grounded=False,
    )

    exchange = NPCExchange(
        user_message=question,
        npc_message=answer,
        source_ids=(),
        state_revision=state.revision,
    )

    turn = NPCChatTurn(
        character_id="C01",
        reply=reply,
        exchange=exchange,
        display_text=answer,
    )

    committed = repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=turn,
    )

    restarted = SQLiteCase001Repository(path)

    assert committed.revision == 1
    assert restarted.load_state(state.session_id) == committed
    assert restarted.load_history(state.session_id, "C01") == (exchange,)


def test_unapproved_social_reply_atomic_rejected(database):
    """등록되지 않은 응답은 저장하지 않는다."""

    repo, state, _ = database

    reply = NPCGroundedReply(
        text="제가 사건의 모든 비밀을 알고 있습니다.",
        source_ids=(),
        grounded=False,
    )

    exchange = NPCExchange(
        user_message="안녕하세요.",
        npc_message=reply.text,
        source_ids=(),
        state_revision=state.revision,
    )

    turn = NPCChatTurn(
        character_id="C01",
        reply=reply,
        exchange=exchange,
    )

    with pytest.raises(ValueError, match="검증되지 않은"):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=turn,
        )

    assert repo.load_state(state.session_id) == state
    assert repo.load_history(state.session_id, "C01") == ()
