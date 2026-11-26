"""Issue #24 - GameState와 NPC 대화 기록 단일 트랜잭션 테스트."""

import sqlite3

import pytest

import crimescene.trigger.atomic_dialogue as module
from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_session import NPCExchange
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository
from crimescene.trigger.case001_dialogue import Case001DialogueResult


def make_state() -> GameState:
    return GameState(
        case_id="CASE-001",
        session_id="ATOMIC-24",
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


def make_turn(state: GameState) -> NPCChatTurn:
    reply = NPCGroundedReply(
        text=FALLBACK_REPLY,
        source_ids=(),
        grounded=False,
    )

    exchange = NPCExchange(
        user_message="안녕하세요?",
        npc_message=FALLBACK_REPLY,
        source_ids=(),
        state_revision=state.revision,
    )

    return NPCChatTurn(
        character_id="C01",
        reply=reply,
        exchange=exchange,
    )


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "issue24.sqlite3"

    repo = SQLiteCase001Repository(path)

    state = make_state()

    repo.save_selection(
        state.session_id,
        "C01",
        state.revision,
    )

    repo.register_state(state)

    return repo, state, path


def test_commit_and_reopen(database):
    """정상 커밋과 재시작 후 복원."""

    repo, state, path = database

    result = repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=make_turn(state),
    )

    assert result.revision == 1

    reopened = SQLiteCase001Repository(path)

    assert reopened.load_state(state.session_id) == result

    assert reopened.load_history(state.session_id, "C01") == (
        make_turn(state).exchange,
    )

    assert reopened.load_selection(state.session_id) == (
        "C01",
        1,
    )


def test_failed_exchange_rolls_back_everything(database):
    """대화 INSERT 실패 시 모든 데이터가 롤백되는지 확인."""

    repo, state, path = database

    # SQLite INSERT 오류를 강제로 발생시킨다.
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TRIGGER fail_exchange
            BEFORE INSERT ON npc_exchanges
            BEGIN
                SELECT RAISE(ABORT, 'injected test failure');
            END
            """
        )

    with pytest.raises(sqlite3.DatabaseError):
        repo.commit_turn(
            expected_state=state,
            updated_state=state.model_copy(update={"revision": 2}),
            turn=make_turn(state),
        )

    # GameState가 변경되지 않았는지 확인
    assert repo.load_state(state.session_id) == state

    # NPC 대화 기록도 남지 않아야 한다.
    assert repo.load_history(state.session_id, "C01") == ()

    # NPC 세션 revision도 유지되어야 한다.
    assert repo.load_selection(state.session_id) == (
        "C01",
        0,
    )


def test_stale_revision_cannot_overwrite(database):
    """오래된 GameState로 중복 커밋할 수 없어야 한다."""

    repo, state, _ = database

    repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=make_turn(state),
    )

    with pytest.raises(ValueError, match="GameState"):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=make_turn(state),
        )

    assert len(repo.load_history(state.session_id, "C01")) == 1


def test_npc_switch_before_commit_blocks_write(database):
    """대화 처리 도중 NPC가 바뀌면 저장을 거부한다."""

    repo, state, _ = database

    repo.save_selection(
        state.session_id,
        "C02",
        state.revision,
    )

    with pytest.raises(ValueError, match="NPC 선택"):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=make_turn(state),
        )

    assert repo.load_state(state.session_id) == state

    assert repo.load_history(state.session_id, "C01") == ()


def test_atomic_wrapper_defers_exchange_write(
    database,
    monkeypatch,
):
    """#23 대화 저장 호출이 실제 DB 쓰기 전에 지연되는지 검증."""

    repo, state, _ = database

    def fake_dialogue(
        question,
        *,
        state,
        session_store,
        resources,
        policies,
        trigger_rules,
        presented_evidence_id,
    ):
        # 대화 시작 전 실제 DB에는 기록이 없어야 한다.
        assert (
            repo.load_history(
                state.session_id,
                "C01",
            )
            == ()
        )

        reply = make_turn(state).reply

        exchange = session_store.append_verified_exchange(
            state,
            "C01",
            user_message=question,
            reply=reply,
        )

        # 기존 세션 저장 API를 호출했지만
        # 실제 SQLite에는 아직 저장되지 않은 상태여야 한다.
        assert (
            repo.load_history(
                state.session_id,
                "C01",
            )
            == ()
        )

        return Case001DialogueResult(
            turn=NPCChatTurn(
                "C01",
                reply,
                exchange,
            ),
            state=state,
            presentation_created=False,
            trigger_ids=(),
            disclosed_card_ids=(),
        )

    monkeypatch.setattr(
        module,
        "run_case001_npc_dialogue",
        fake_dialogue,
    )

    result = module.run_case001_npc_dialogue_atomic(
        "안녕하세요?",
        session_id=state.session_id,
        repository=repo,
        resources=None,
        policies={},
        trigger_rules=(),
    )

    assert result.state.revision == 1

    assert len(repo.load_history(state.session_id, "C01")) == 1

# ============================================================
# Issue #172 - atomic memory recall
# ============================================================

RECALL_QUESTION = "제가 아까 어떤 질문을 했는지 기억하세요?"
PREVIOUS_QUESTION = "방금 말씀하신 내용을 좀 더 자세히 설명해 주세요."
RECALL_ANSWER = "네. 직전 답변을 더 설명해 달라고 하셨습니다."


def make_recall_database(tmp_path):
    path = tmp_path / "issue172-recall.sqlite3"
    repo = SQLiteCase001Repository(path)

    state = make_state().model_copy(
        update={"content_version": "case001_1120"}
    )

    repo.save_selection(
        state.session_id,
        "C01",
        state.revision,
    )

    repo.register_state(state)

    return repo, state, path


def make_memory_turn(
    state,
    *,
    question=RECALL_QUESTION,
    answer=RECALL_ANSWER,
    character_id="C01",
):
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

    return NPCChatTurn(
        character_id=character_id,
        reply=reply,
        exchange=exchange,
        display_text=answer,
    )


def seed_previous_question(repo, state):
    return repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=make_memory_turn(
            state,
            question=PREVIOUS_QUESTION,
            answer=FALLBACK_REPLY,
        ),
    )


def test_atomic_recall_commit_and_reopen(tmp_path):
    repo, state, path = make_recall_database(tmp_path)

    state = seed_previous_question(repo, state)

    turn = make_memory_turn(state)

    result = repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=turn,
    )

    assert result.revision == state.revision + 1

    assert result == state.model_copy(
        update={"revision": state.revision + 1}
    )

    reopened = SQLiteCase001Repository(path)

    history = reopened.load_history(
        state.session_id,
        "C01",
    )

    assert len(history) == 2
    assert history[-1].npc_message == RECALL_ANSWER
    assert history[-1].source_ids == ()
    assert reopened.load_state(state.session_id) == result


def test_atomic_recall_without_history(tmp_path):
    repo, state, _ = make_recall_database(tmp_path)

    answer = "아직 저와 나눈 대화가 없습니다."

    result = repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=make_memory_turn(
            state,
            answer=answer,
        ),
    )

    assert result.revision == state.revision + 1

    history = repo.load_history(
        state.session_id,
        "C01",
    )

    assert len(history) == 1
    assert history[0].npc_message == answer


def test_atomic_recall_rejects_fabricated_history(tmp_path):
    repo, state, _ = make_recall_database(tmp_path)

    with pytest.raises(ValueError, match="기억 응답"):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=make_memory_turn(state),
        )

    assert repo.load_state(state.session_id) == state
    assert repo.load_history(state.session_id, "C01") == ()

    assert repo.load_selection(state.session_id) == (
        "C01",
        state.revision,
    )


def test_atomic_recall_rejects_forged_answer(tmp_path):
    repo, state, _ = make_recall_database(tmp_path)

    state = seed_previous_question(repo, state)

    with pytest.raises(ValueError):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=make_memory_turn(
                state,
                answer="PRIVATE_UNVERIFIED_ANSWER",
            ),
        )

    assert repo.load_state(state.session_id) == state
    assert len(repo.load_history(state.session_id, "C01")) == 1


def test_atomic_recall_cannot_use_other_npc_history(tmp_path):
    repo, state, _ = make_recall_database(tmp_path)

    state = seed_previous_question(repo, state)

    repo.save_selection(
        state.session_id,
        "C02",
        state.revision,
    )

    with pytest.raises(ValueError, match="기억 응답"):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=make_memory_turn(
                state,
                character_id="C02",
            ),
        )

    assert repo.load_state(state.session_id) == state
    assert repo.load_history(state.session_id, "C02") == ()
    assert len(repo.load_history(state.session_id, "C01")) == 1


def test_atomic_recall_cannot_use_other_session_history(tmp_path):
    repo, state, _ = make_recall_database(tmp_path)

    state = seed_previous_question(repo, state)

    other = make_state().model_copy(
        update={
            "session_id": "ATOMIC-172-OTHER",
            "content_version": "case001_1120",
        }
    )

    repo.save_selection(
        other.session_id,
        "C01",
        other.revision,
    )

    repo.register_state(other)

    with pytest.raises(ValueError, match="기억 응답"):
        repo.commit_turn(
            expected_state=other,
            updated_state=other,
            turn=make_memory_turn(other),
        )

    assert repo.load_state(other.session_id) == other
    assert repo.load_history(other.session_id, "C01") == ()
    assert len(repo.load_history(state.session_id, "C01")) == 1


def test_atomic_recall_stale_revision_is_rejected(tmp_path):
    repo, state, _ = make_recall_database(tmp_path)

    state = seed_previous_question(repo, state)

    turn = make_memory_turn(state)

    committed = repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=turn,
    )

    with pytest.raises(ValueError):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=turn,
        )

    assert repo.load_state(state.session_id) == committed
    assert len(repo.load_history(state.session_id, "C01")) == 2

# Issue #172 - verified display persistence

DISPLAY_SOURCE = "K-C01-01"
DISPLAY_QUOTE = "당시 서로 의견이 달랐습니다."

DISPLAY_CANONICAL = (
    "제가 확인한 자료에는 이렇게 나와 있어요.\n"
    f"“{DISPLAY_QUOTE}” (근거: {DISPLAY_SOURCE})"
)

DISPLAY_EXPECTED = (
    "이 부분부터 말씀드리겠습니다.\n"
    f"“{DISPLAY_QUOTE}”"
)


def make_display_turn(
    state,
    *,
    stored_display=DISPLAY_EXPECTED,
    actual_display=DISPLAY_EXPECTED,
):
    reply = NPCGroundedReply(
        text=DISPLAY_CANONICAL,
        source_ids=(DISPLAY_SOURCE,),
        grounded=True,
    )

    exchange = NPCExchange(
        user_message="피해자와 어떤 관계였나요?",
        npc_message=DISPLAY_CANONICAL,
        source_ids=(DISPLAY_SOURCE,),
        state_revision=state.revision,
        display_text=stored_display,
    )

    return NPCChatTurn(
        character_id="C01",
        reply=reply,
        exchange=exchange,
        display_text=actual_display,
    )


def test_display_persistence_and_reopen(tmp_path):
    from crimescene.chat.npc_history_display import (
        render_stored_npc_message,
    )

    repo, state, path = make_recall_database(tmp_path)

    turn = make_display_turn(state)

    committed = repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=turn,
    )

    reopened = SQLiteCase001Repository(path)

    exchange = reopened.load_history(
        state.session_id,
        "C01",
    )[0]

    assert reopened.load_state(state.session_id) == committed

    assert exchange.npc_message == DISPLAY_CANONICAL
    assert exchange.source_ids == (DISPLAY_SOURCE,)
    assert exchange.display_text == DISPLAY_EXPECTED

    assert render_stored_npc_message(
        exchange.npc_message,
        exchange.source_ids,
        character_id="C01",
        stored_display=exchange.display_text,
    ) == DISPLAY_EXPECTED


@pytest.mark.parametrize(
    "forged",
    [
        DISPLAY_EXPECTED + "\nPRIVATE_SENTINEL",
        DISPLAY_EXPECTED.replace(
            DISPLAY_QUOTE,
            "검증하지 않은 사건 내용입니다.",
        ),
        DISPLAY_EXPECTED.replace(
            "이 부분부터 말씀드리겠습니다.",
            "핵심만 말씀드리죠.",
        ),
        DISPLAY_CANONICAL,
    ],
)
def test_atomic_display_rejects_forged_content(
    tmp_path,
    forged,
):
    repo, state, _ = make_recall_database(tmp_path)

    with pytest.raises(ValueError, match="화면 응답"):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=make_display_turn(
                state,
                stored_display=forged,
                actual_display=forged,
            ),
        )

    assert repo.load_state(state.session_id) == state
    assert repo.load_history(state.session_id, "C01") == ()


def test_atomic_display_rejects_turn_mismatch(tmp_path):
    repo, state, _ = make_recall_database(tmp_path)

    with pytest.raises(ValueError, match="화면 응답"):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=make_display_turn(
                state,
                actual_display="PRIVATE_SENTINEL",
            ),
        )

    assert repo.load_state(state.session_id) == state
    assert repo.load_history(state.session_id, "C01") == ()


def test_corrupted_display_fails_closed():
    from crimescene.chat.npc_history_display import (
        render_stored_npc_message,
    )

    assert render_stored_npc_message(
        DISPLAY_CANONICAL,
        (DISPLAY_SOURCE,),
        character_id="C01",
        stored_display="PRIVATE_SENTINEL",
    ) == FALLBACK_REPLY


def test_old_database_migrates_without_losing_history(tmp_path):
    repo, state, path = make_recall_database(tmp_path)

    state = seed_previous_question(repo, state)

    # Simulate a pre-migration database using an isolated test DB.
    with sqlite3.connect(path) as db:
        db.execute(
            "ALTER TABLE npc_exchanges DROP COLUMN display_text"
        )

    reopened = SQLiteCase001Repository(path)

    # Repeated initialization must remain safe.
    reopened = SQLiteCase001Repository(path)

    history = reopened.load_history(
        state.session_id,
        "C01",
    )

    assert len(history) == 1
    assert history[0].user_message == PREVIOUS_QUESTION
    assert history[0].display_text is None

    reopened.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=make_display_turn(state),
    )

    history = reopened.load_history(
        state.session_id,
        "C01",
    )

    assert len(history) == 2
    assert history[0].display_text is None
    assert history[1].display_text == DISPLAY_EXPECTED


def test_regular_repository_preserves_display(tmp_path):
    from crimescene.chat.npc_session_repository import (
        SQLiteNPCSessionRepository,
    )

    path = tmp_path / "display-session.sqlite3"
    repo = SQLiteNPCSessionRepository(path)

    state = make_state().model_copy(
        update={"content_version": "case001_1120"}
    )

    repo.save_selection(
        state.session_id,
        "C01",
        state.revision,
    )

    turn = make_display_turn(state)

    repo.append_exchange(
        state.session_id,
        "C01",
        turn.exchange,
    )

    reopened = SQLiteNPCSessionRepository(path)

    assert reopened.load_history(
        state.session_id,
        "C01",
    ) == (turn.exchange,)


def test_regular_repository_rejects_forged_display(tmp_path):
    from crimescene.chat.npc_session_repository import (
        SQLiteNPCSessionRepository,
    )

    repo = SQLiteNPCSessionRepository(
        tmp_path / "invalid-display.sqlite3"
    )

    state = make_state()

    repo.save_selection(
        state.session_id,
        "C01",
        state.revision,
    )

    turn = make_display_turn(
        state,
        stored_display="PRIVATE_SENTINEL",
    )

    with pytest.raises(ValueError):
        repo.append_exchange(
            state.session_id,
            "C01",
            turn.exchange,
        )

    assert repo.load_history(state.session_id, "C01") == ()
