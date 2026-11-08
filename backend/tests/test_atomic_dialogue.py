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
