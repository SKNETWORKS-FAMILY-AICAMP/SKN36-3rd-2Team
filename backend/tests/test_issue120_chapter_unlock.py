"""Issue #120 - 서버 측 챕터 해금 검증."""

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.chapter_progress import (
    ChapterUnlockRule,
    advance_chapter,
    advance_chapter_atomic,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def make_state(**changes):
    data = create_initial_state("chapter-unlock-test").model_dump()
    data["phase"] = GamePhase.INVESTIGATION
    data.update(changes)
    return GameState.model_validate(data)


def make_rule():
    # 테스트용 조건이며 실제 스토리 해금 조건은 아닙니다.
    return ChapterUnlockRule(
        target_chapter="CH01",
        required_evidence=frozenset({"E01"}),
        required_flags=frozenset({"TEST_CH01_READY"}),
        required_presentations=frozenset({"C01:E01"}),
    )


def ready_state():
    return make_state(
        evidence={"E01": EvidenceState(stage="found")},
        flags=["TEST_CH01_READY"],
        presented={"C01": ["E01"]},
    )


def test_chapter_unlock_success():
    original = ready_state()
    updated = advance_chapter(original, rule=make_rule())

    assert original.current_chapter == "CH00"
    assert updated.current_chapter == "CH01"
    assert updated.unlocked_chapters == ["CH00", "CH01"]
    assert updated.revision == original.revision + 1


def test_missing_rule_is_rejected():
    with pytest.raises(PermissionError):
        advance_chapter(ready_state(), rule=None)


def test_empty_rule_is_rejected():
    with pytest.raises(ValueError):
        ChapterUnlockRule(target_chapter="CH01")


def test_missing_evidence_is_rejected():
    state = ready_state().model_copy(update={"evidence": {}})

    with pytest.raises(PermissionError):
        advance_chapter(state, rule=make_rule())


def test_missing_flag_is_rejected():
    state = ready_state().model_copy(update={"flags": []})

    with pytest.raises(PermissionError):
        advance_chapter(state, rule=make_rule())


def test_missing_presentation_is_rejected():
    state = ready_state().model_copy(update={"presented": {}})

    with pytest.raises(PermissionError):
        advance_chapter(state, rule=make_rule())


def test_chapter_skip_is_rejected():
    rule = ChapterUnlockRule(
        target_chapter="CH02",
        required_evidence=frozenset({"E01"}),
    )

    with pytest.raises(PermissionError):
        advance_chapter(ready_state(), rule=rule)


def test_prologue_cannot_unlock_chapter():
    state = ready_state().model_copy(update={"phase": GamePhase.PROLOGUE})

    with pytest.raises(PermissionError):
        advance_chapter(state, rule=make_rule())


def test_unexpected_unlock_history_is_rejected():
    state = make_state(
        unlocked_chapters=["CH00", "CH01"],
        current_chapter="CH00",
    )

    with pytest.raises(ValueError):
        advance_chapter(state, rule=make_rule())


def test_chapter_unlock_persists_atomically(tmp_path):
    """실제 게임 세션의 챕터 전환을 DB에 저장합니다."""

    repository = SQLiteCase001Repository(tmp_path / "chapter.sqlite3")
    app = create_app(
        repository,
        session_secret="chapter-unlock-secret-" + "a" * 40,
    )

    with TestClient(app) as client:
        response = client.post("/api/games")
        assert response.status_code == 201

        session_id = response.json()["sessionId"]

        response = client.post(f"/api/games/{session_id}/prologue/complete")
        assert response.status_code == 200

        current = repository.load_state(session_id)

        # 테스트 설정: 플레이어가 필요한 행동을 완료한 상태
        ready = GameState.model_validate(
            {
                **current.model_dump(mode="python"),
                "evidence": {
                    "E01": {"stage": "found"},
                },
                "flags": ["TEST_CH01_READY"],
                "presented": {"C01": ["E01"]},
                "revision": current.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=current,
            updated_state=ready,
        )

        updated = advance_chapter_atomic(
            repository,
            session_id,
            rule=make_rule(),
        )

        persisted = repository.load_state(session_id)

        assert persisted == updated
        assert persisted.current_chapter == "CH01"
        assert persisted.unlocked_chapters == ["CH00", "CH01"]


def test_stale_state_cannot_overwrite_chapter(tmp_path):
    """revision이 지난 상태는 챕터 변경을 덮어쓰지 못합니다."""

    repository = SQLiteCase001Repository(tmp_path / "stale.sqlite3")
    app = create_app(
        repository,
        session_secret="stale-chapter-secret-" + "b" * 40,
    )

    with TestClient(app) as client:
        session_id = client.post("/api/games").json()["sessionId"]
        client.post(f"/api/games/{session_id}/prologue/complete")

        original = repository.load_state(session_id)

        ready = GameState.model_validate(
            {
                **original.model_dump(mode="python"),
                "evidence": {"E01": {"stage": "found"}},
                "flags": ["TEST_CH01_READY"],
                "presented": {"C01": ["E01"]},
                "revision": original.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=original,
            updated_state=ready,
        )

        updated = advance_chapter(ready, rule=make_rule())

        with pytest.raises(ValueError):
            repository.commit_state(
                expected_state=original,
                updated_state=updated,
            )
