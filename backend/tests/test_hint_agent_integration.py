
"""Issue #133 - Hint Agent SQLite 통합 및 챕터 접근 검증."""

from fastapi.testclient import TestClient

from crimescene.agents.contracts import AgentContext, AgentRequest, AgentType
from crimescene.agents.hint_agent import HintAgent
from crimescene.agents.orchestrator import AgentOrchestrator
from crimescene.agents.registry import AgentRegistry
from crimescene.api.app import create_app
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

SESSION_SECRET = "hint-test-" + "x" * 40


def make_rules():
    return {
        "E01": EvidenceRule(
            name="공개 증거",
            score=2,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
        "E02": EvidenceRule(
            name="아직 공개되지 않은 증거",
            score=3,
            holder="C02",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
    }


def make_runtime(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")

    app = create_app(
        repository,
        session_secret=SESSION_SECRET,
    )

    agent = HintAgent(
        load_state=repository.load_state,
        evidence_rules=make_rules(),
    )

    orchestrator = AgentOrchestrator(
        AgentRegistry([agent]),
        load_state=repository.load_state,
    )

    return app, repository, orchestrator


def start_game(client):
    response = client.post("/api/games")
    assert response.status_code == 201

    session_id = response.json()["sessionId"]

    completed = client.post(
        f"/api/games/{session_id}/prologue/complete"
    )
    assert completed.status_code == 200

    return session_id


def request_hint(orchestrator, repository, session_id, level):
    state = repository.load_state(session_id)

    return orchestrator.execute(
        AgentRequest(
            agent_type=AgentType.HINT,
            message=f"{level}단계 힌트",
        ),
        context=AgentContext.from_game_state(state),
    )


def test_hint_levels_do_not_modify_sqlite(tmp_path):
    """힌트 3단계를 실행해도 DB revision과 기록이 유지됩니다."""

    app, repository, orchestrator = make_runtime(tmp_path)

    with TestClient(app) as client:
        session_id = start_game(client)

        before = repository.load_state(session_id).model_dump(mode="json")
        selection_before = repository.load_selection(session_id)
        history_before = repository.load_history(session_id, "C01")

        for level in (1, 2, 3):
            result = request_hint(
                orchestrator,
                repository,
                session_id,
                level,
            )

            assert result.agent_type == AgentType.HINT
            assert result.level == level
            assert result.source_ids == ()

        after = repository.load_state(session_id).model_dump(mode="json")

        assert after == before
        assert repository.load_selection(session_id) == selection_before
        assert repository.load_history(session_id, "C01") == history_before


def test_hint_only_reports_current_chapter(tmp_path):
    """현재 해금된 챕터만 힌트 응답에 표시합니다."""

    app, repository, orchestrator = make_runtime(tmp_path)

    with TestClient(app) as client:
        session_id = start_game(client)
        original = repository.load_state(session_id)

        # 테스트용으로 챕터 진행 상태를 구성합니다.
        updated = GameState.model_validate(
            {
                **original.model_dump(mode="python"),
                "current_chapter": "CH01",
                "unlocked_chapters": ["CH00", "CH01"],
                "revision": original.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=original,
            updated_state=updated,
        )

        result = request_hint(
            orchestrator,
            repository,
            session_id,
            1,
        )

        assert result.chapter == "CH01"
        assert "CH01" in result.text

        for locked_chapter in ("CH02", "CH03", "CH04"):
            assert locked_chapter not in result.text

        assert repository.load_state(session_id).revision == updated.revision


def test_hint_does_not_disclose_uncollected_evidence(tmp_path):
    """미획득 증거의 이름·ID가 힌트 응답에 노출되지 않습니다."""

    app, repository, orchestrator = make_runtime(tmp_path)

    with TestClient(app) as client:
        session_id = start_game(client)

        for level in (1, 2, 3):
            result = request_hint(
                orchestrator,
                repository,
                session_id,
                level,
            )

            serialized = result.model_dump_json()

            assert "E02" not in serialized
            assert "아직 공개되지 않은 증거" not in serialized
            assert result.source_ids == ()
