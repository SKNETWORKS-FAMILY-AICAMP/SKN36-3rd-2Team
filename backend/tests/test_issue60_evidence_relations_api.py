"""Issue #60: collected evidence details must not leak locked relationships."""

from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def _edge(
    case_id: str,
    edge_id: str,
    target: str,
    *,
    required_evidence: list[str],
    access_scope: str = "conditional",
    required_ending: str | None = None,
) -> RelationshipSourceEdge:
    return RelationshipSourceEdge(
        case_id=case_id,
        edge_id=edge_id,
        source_id="C01",
        target_id=target,
        relation=f"테스트 관계 {target}",
        incident_year=2016,
        valid_from=date(2016, 1, 1),
        valid_to=date(2016, 12, 31),
        temporal_precision="day",
        truth_status="documented",
        source_doc_ids=[],
        asserted_by=[],
        access_scope=access_scope,
        required_evidence=required_evidence,
        required_presentations=[],
        required_flags=[],
        required_ending=required_ending,
    )


def test_evidence_relations_only_reveal_accessible_connections(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "issue60.sqlite3")
    app = create_app(repository, session_secret="issue60-test-" + "x" * 40)
    app.state.dialogue_resources = SimpleNamespace(
        evidence_rules={
            "E01": EvidenceRule(
                name="테스트 증거",
                score=2,
                holder="C01",
                prerequisites=[],
                presentation=[],
                q=[],
            )
        },
    )

    with TestClient(app) as client:
        created = client.post("/api/games")
        assert created.status_code == 201
        sid = created.json()["sessionId"]
        started = client.post(f"/api/games/{sid}/prologue/complete")
        assert started.status_code == 200

        # 미수집 증거는 상세 정보의 존재 자체를 숨깁니다.
        assert client.get(f"/api/games/{sid}/evidence/E01").status_code == 404

        old = repository.load_state(sid)
        app.state.dialogue_resources.trusted_edges = (
            _edge(old.case_id, "REL-001", "C02", required_evidence=["E01"]),
            _edge(old.case_id, "REL-002", "C03", required_evidence=["E02"]),
            _edge(
                old.case_id,
                "REL-003",
                "C04",
                required_evidence=[],
                access_scope="ending_only",
                required_ending="SUCCESS",
            ),
        )
        changed = GameState.model_validate(
            {
                **old.model_dump(mode="python"),
                "evidence": {"E01": EvidenceState(stage="found").model_dump()},
                "unlocked_characters": ["C01", "C02", "C03", "C04"],
                "score": 2,
                "revision": old.revision + 1,
            }
        )
        repository.commit_state(expected_state=old, updated_state=changed)

        response = client.get(f"/api/games/{sid}/evidence/E01")
        assert response.status_code == 200, response.text
        detail = response.json()
        assert detail["confirmedRelations"] == [
            {"id": "C02", "label": "테스트 관계 C02"}
        ]
        assert "테스트 관계 C03" not in response.text
        assert "테스트 관계 C04" not in response.text
        assert detail["documents"] == []
