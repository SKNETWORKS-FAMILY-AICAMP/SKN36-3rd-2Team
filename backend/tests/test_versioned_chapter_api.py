"""Issue #165 - versioned chapter API integration."""

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.chapter_progress import ChapterUnlockRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "expanded-chapter.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="issue165-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"

    app.state.chapter_unlock_rules = {
        chapter: ChapterUnlockRule(
            target_chapter=chapter,
            required_flags=frozenset({"TEST_READY"}),
        )
        for chapter in (
            "CH01",
            "CH02",
            "CH03",
            "CH04",
        )
    }

    with TestClient(app) as client:
        response = client.post("/api/games")
        assert response.status_code == 201

        session_id = response.json()["sessionId"]

        response = client.post(
            f"/api/games/{session_id}/prologue/complete"
        )
        assert response.status_code == 200

        state = repository.load_state(session_id)

        updated = GameState.model_validate({
            **state.model_dump(),
            "flags": ["TEST_READY"],
            "revision": state.revision + 1,
        })

        repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )

        yield app, client, repository, session_id


def advance(client, repository, session_id, target=None):
    state = repository.load_state(session_id)

    payload = {
        "expectedRevision": state.revision,
    }

    if target is not None:
        payload["targetChapter"] = target

    return client.post(
        f"/api/games/{session_id}/chapter/advance",
        json=payload,
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("CH02", "CH03"),
        ("CH03", "CH02"),
    ],
)
def test_expanded_api_branch_order(runtime, first, second):
    _, client, repository, session_id = runtime

    for target in ("CH01", first, second, "CH04"):
        before = repository.load_state(session_id)

        response = advance(
            client, repository, session_id, target
        )

        assert response.status_code == 200

        after = repository.load_state(session_id)

        assert after.current_chapter == target
        assert after.revision == before.revision + 1
        assert after.content_version == "case001_1120"

    assert after.unlocked_chapters == [
        "CH00",
        "CH01",
        first,
        second,
        "CH04",
    ]


def test_expanded_branch_requires_selection(runtime):
    _, client, repository, session_id = runtime

    response = advance(
        client, repository, session_id
    )
    assert response.status_code == 200

    before = repository.load_state(session_id)

    response = advance(
        client, repository, session_id
    )

    assert response.status_code == 422
    assert repository.load_state(session_id) == before


def test_expanded_chapter_skip_denied(runtime):
    _, client, repository, session_id = runtime

    before = repository.load_state(session_id)

    response = advance(
        client, repository, session_id, "CH04"
    )

    assert response.status_code == 409
    assert repository.load_state(session_id) == before


def test_runtime_version_mismatch_denied(runtime):
    app, client, repository, session_id = runtime

    before = repository.load_state(session_id)

    app.state.content_version = "case001_v7_1"

    response = client.get(
        f"/api/games/{session_id}"
    )

    assert response.status_code == 409
    assert repository.load_state(session_id) == before


def test_session_version_cannot_be_changed(runtime):
    _, _, repository, session_id = runtime

    before = repository.load_state(session_id)

    updated = GameState.model_validate({
        **before.model_dump(),
        "content_version": "case001_v7_1",
        "revision": before.revision + 1,
    })

    with pytest.raises(ValueError):
        repository.commit_state(
            expected_state=before,
            updated_state=updated,
        )

    assert repository.load_state(session_id) == before
