"""Issue #23 - SQLite NPC 대화 영구 저장소 테스트."""

import pytest

from crimescene.chat.npc_session import NPCExchange
from crimescene.chat.npc_session_repository import (
    SQLiteNPCSessionRepository,
)


@pytest.fixture
def repository(tmp_path):
    return SQLiteNPCSessionRepository(tmp_path / "npc_sessions.sqlite3")


def make_exchange(
    question="안녕하세요?",
    answer="네, 말씀하세요.",
    revision=0,
):
    return NPCExchange(
        user_message=question,
        npc_message=answer,
        source_ids=("K-C01-01",),
        state_revision=revision,
    )


def test_save_and_load_selection(repository):
    repository.save_selection("S001", "C01", 0)

    assert repository.load_selection("S001") == ("C01", 0)


def test_unknown_session(repository):
    assert repository.load_selection("UNKNOWN") is None


def test_npc_switch_persists(repository):
    repository.save_selection("S001", "C01", 0)
    repository.save_selection("S001", "C02", 1)

    assert repository.load_selection("S001") == ("C02", 1)


def test_old_revision_rejected(repository):
    repository.save_selection("S001", "C01", 5)

    with pytest.raises(ValueError, match="revision"):
        repository.save_selection("S001", "C02", 3)


def test_append_and_load_history(repository):
    repository.save_selection("S001", "C01", 0)

    exchange = make_exchange()

    repository.append_exchange("S001", "C01", exchange)

    assert repository.load_history("S001", "C01") == (exchange,)


def test_persistence_after_reopen(tmp_path):
    path = tmp_path / "persistent.sqlite3"

    first = SQLiteNPCSessionRepository(path)
    first.save_selection("S001", "C01", 0)

    exchange = make_exchange()
    first.append_exchange("S001", "C01", exchange)

    # 새로운 저장소 객체에서 기존 기록을 읽는다.
    second = SQLiteNPCSessionRepository(path)

    assert second.load_selection("S001") == ("C01", 0)
    assert second.load_history("S001", "C01") == (exchange,)


def test_npc_histories_are_isolated(repository):
    repository.save_selection("S001", "C01", 0)

    repository.append_exchange(
        "S001",
        "C01",
        make_exchange(),
    )

    repository.save_selection("S001", "C02", 0)

    assert repository.load_history("S001", "C02") == ()
    assert len(repository.load_history("S001", "C01")) == 1


def test_game_sessions_are_isolated(repository):
    repository.save_selection("S001", "C01", 0)
    repository.save_selection("S002", "C01", 0)

    repository.append_exchange(
        "S001",
        "C01",
        make_exchange(),
    )

    assert len(repository.load_history("S001", "C01")) == 1
    assert repository.load_history("S002", "C01") == ()


def test_inactive_npc_cannot_append(repository):
    repository.save_selection("S001", "C01", 0)

    with pytest.raises(PermissionError):
        repository.append_exchange(
            "S001",
            "C02",
            make_exchange(),
        )


def test_missing_session_cannot_append(repository):
    with pytest.raises(ValueError, match="등록되지 않은"):
        repository.append_exchange(
            "UNKNOWN",
            "C01",
            make_exchange(),
        )


def test_history_limit(tmp_path):
    repository = SQLiteNPCSessionRepository(
        tmp_path / "limited.sqlite3",
        max_exchanges_per_npc=2,
    )

    repository.save_selection("S001", "C01", 0)

    for index in range(3):
        repository.append_exchange(
            "S001",
            "C01",
            make_exchange(
                question=f"질문 {index}",
                answer=f"응답 {index}",
            ),
        )

    history = repository.load_history("S001", "C01")

    assert len(history) == 2
    assert history[0].user_message == "질문 1"
    assert history[1].user_message == "질문 2"


def test_delete_session_cascades(repository):
    repository.save_selection("S001", "C01", 0)

    repository.append_exchange(
        "S001",
        "C01",
        make_exchange(),
    )

    repository.delete_session("S001")

    assert repository.load_selection("S001") is None
    assert repository.load_history("S001", "C01") == ()


def test_sql_injection_string_is_data(repository):
    session_id = "S001'; DROP TABLE npc_sessions; --"

    repository.save_selection(session_id, "C01", 0)

    assert repository.load_selection(session_id) == ("C01", 0)

    repository.save_selection("S002", "C02", 0)
    assert repository.load_selection("S002") == ("C02", 0)


def test_invalid_npc_rejected(repository):
    with pytest.raises(ValueError, match="NPC ID"):
        repository.save_selection("S001", "C11", 0)


def test_invalid_exchange_rejected(repository):
    repository.save_selection("S001", "C01", 0)

    with pytest.raises(TypeError):
        repository.append_exchange(
            "S001",
            "C01",
            "검증되지 않은 메시지",
        )


def test_old_exchange_revision_rejected(repository):
    repository.save_selection("S001", "C01", 5)

    with pytest.raises(ValueError, match="revision"):
        repository.append_exchange(
            "S001",
            "C01",
            make_exchange(revision=3),
        )


def test_empty_session_id_rejected(repository):
    with pytest.raises(ValueError, match="세션 ID"):
        repository.save_selection("", "C01", 0)
