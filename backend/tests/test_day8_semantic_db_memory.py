"""Semantic recall with real SQLite persistence."""

import sqlite3

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from crimescene.chat import npc_chat_runtime as runtime
from crimescene.chat import npc_semantic_router as router

from crimescene.chat.npc_session import NPCSessionStore
from crimescene.scenario.schemas.game_state import GamePhase

from crimescene.trigger.atomic_dialogue import (
    SQLiteCase001Repository,
    _StagedSessionRepository,
)

from test_atomic_dialogue import make_state


@pytest.fixture
def db_environment(tmp_path, monkeypatch):

    monkeypatch.setenv(
        "CRIMESCENE_ENABLE_SEMANTIC_DIALOGUE",
        "true",
    )

    path = tmp_path / "semantic_memory.sqlite3"

    repo = SQLiteCase001Repository(path)

    state = make_state().model_copy(
        update={
            "content_version": "case001_1120",
            "phase": GamePhase.INVESTIGATION,
        }
    )

    repo.save_selection(
        state.session_id,
        "C01",
        state.revision,
    )

    repo.register_state(state)

    return path, repo, state


def chat(repo, state, question):

    staged = _StagedSessionRepository(repo)

    store = NPCSessionStore(repository=staged)

    generate = MagicMock()

    turn = runtime.run_npc_chat(
        question,
        state=state,
        session_store=store,
        resources=None,
        generate=generate,
    )

    assert staged.pending == turn.exchange

    generate.assert_not_called()

    return turn


@pytest.mark.parametrize(
    ("route", "question", "prefix"),
    [
        (
            "RECALL_FIRST",
            "우리 처음에 무슨 얘기 했더라?",
            "처음 대화요?",
        ),
        (
            "RECALL_LAST",
            "아까 내가 뭘 물어봤지?",
            "아까 대화요?",
        ),
    ],
)
def test_recall_after_database_reopen(
    db_environment,
    monkeypatch,
    route,
    question,
    prefix,
):
    path, repo, state = db_environment

    monkeypatch.setattr(
        router,
        "generate_response",
        MagicMock(return_value="TALK"),
    )

    first = chat(
        repo,
        state,
        "어, 안녕. 잠깐 시간 돼요?",
    )

    state = repo.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=first,
    )

    # 저장소 재생성: 이전 Python 객체의 메모리에 의존하지 않는다.
    reopened = SQLiteCase001Repository(path)

    state = reopened.load_state(state.session_id)

    monkeypatch.setattr(
        router,
        "generate_response",
        MagicMock(return_value=route),
    )

    recall = chat(
        reopened,
        state,
        question,
    )

    assert recall.reply.text.startswith(prefix)
    assert "이야기할 수 있냐고" in recall.reply.text
    assert not recall.reply.grounded
    assert recall.reply.source_ids == ()

    state = reopened.commit_turn(
        expected_state=state,
        updated_state=state,
        turn=recall,
    )

    final = SQLiteCase001Repository(path)

    history = final.load_history(
        state.session_id,
        "C01",
    )

    assert len(history) == 2
    assert history[-1].npc_message == recall.reply.text

    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM npc_exchanges"
        ).fetchone()[0] == 2


def test_forged_semantic_memory_rejected(
    db_environment,
    monkeypatch,
):
    _, repo, state = db_environment

    monkeypatch.setattr(
        router,
        "generate_response",
        MagicMock(return_value="RECALL_FIRST"),
    )

    turn = chat(
        repo,
        state,
        "우리 처음에 어떤 얘기 했어?",
    )

    forged = "처음 대화요? 존재하지 않는 사건 진술입니다."

    fake_turn = replace(
        turn,
        reply=replace(turn.reply, text=forged),
        exchange=replace(
            turn.exchange,
            npc_message=forged,
        ),
        display_text=forged,
    )

    with pytest.raises(ValueError):
        repo.commit_turn(
            expected_state=state,
            updated_state=state,
            turn=fake_turn,
        )

    assert repo.load_history(
        state.session_id,
        "C01",
    ) == ()

    assert repo.load_state(
        state.session_id
    ) == state
