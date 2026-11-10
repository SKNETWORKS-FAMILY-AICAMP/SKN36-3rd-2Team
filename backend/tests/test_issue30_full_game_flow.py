"""Issue #30 - 게임 시작부터 엔딩까지 API 통합 테스트."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.loaders.unlock_graph_loader import Case001UnlockRules
from crimescene.scenario.npc_unlock import NPCUnlockRule
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def test_full_game_flow(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "issue30.sqlite3")
    app = create_app(
        repository,
        session_secret="issue30-test-" + "x" * 40,
    )

    scores = [1, 2, 3, 2, 3, 3, 2, 2, 1, 2]

    rules = {
        f"E{i:02d}": EvidenceRule(
            name=f"테스트 증거 {i}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for i, score in enumerate(scores, start=1)
    }

    policies = {
        f"POL-E{i:02d}": AccessPolicy(
            required_character="C01",
            required_disclosed_cards=["KC01-TEST"],
            required_evidence=[],
            required_presentations=[],
            required_flags=[],
            required_ending=None,
            required_topics=[],
        )
        for i in range(1, 6)
    }

    evaluator = PolicyEvaluator(policies)

    app.state.dialogue_resources = SimpleNamespace(
        evidence_rules=rules,
        evaluator=evaluator,
    )
    app.state.acquisition_evaluator = evaluator
    app.state.acquisition_policy_ids = {
        f"E{i:02d}": f"POL-E{i:02d}" for i in range(1, 6)
    }

    app.state.dialogue_flag_config = Case001UnlockRules(
        npc_rules={
            "C02": NPCUnlockRule(required_evidence=frozenset({"E01"})),
            "C03": NPCUnlockRule(required_evidence=frozenset({"E02"})),
        },
        flag_requirements={},
        flag_sources={},
    )

    # 실제 사건 정답이 아닌 테스트 전용 데이터입니다.
    app.state.case_truth = CaseTruth(
        case_id="CASE-001",
        perpetrator_character_id="C03",
        motive="test motive",
        cause_of_death="test cause",
        crime_method="test method",
        crime_event_id="EVT-TEST",
    )

    with TestClient(app) as client:
        # 1. 새 게임 생성
        created = client.post("/api/games")
        assert created.status_code == 201
        sid = created.json()["sessionId"]
        path = f"/api/games/{sid}"

        assert created.json()["phase"] == "PROLOGUE"
        assert created.json()["attemptsLeft"] == 3

        # 2. 프롤로그 종료
        started = client.post(f"{path}/prologue/complete")
        assert started.status_code == 200
        assert started.json()["phase"] == "INVESTIGATION"

        # 3. NPC 지식 공개 전에는 증거 수집 불가
        blocked = client.post(f"{path}/evidence/E01/collect")
        assert blocked.status_code == 403

        # NPC 대화로 카드가 공개된 상황을 서버에 구성합니다.
        original = repository.load_state(sid)
        disclosed = GameState.model_validate(
            {
                **original.model_dump(),
                "disclosed_cards": ["KC01-TEST"],
                "revision": original.revision + 1,
            }
        )
        repository.commit_state(
            expected_state=original,
            updated_state=disclosed,
        )

        # 4. 증거 5개 수집 및 NPC 해금
        for i in range(1, 6):
            response = client.post(f"{path}/evidence/E{i:02d}/collect")
            assert response.status_code == 200, response.text
            assert response.json()["created"] is True

        game = client.get(path).json()
        evidence = client.get(f"{path}/evidence").json()

        assert game["collection"]["score"] == 11
        assert game["canAccuse"] is True
        assert evidence["collectedCount"] == 5
        assert {"C02", "C03"}.issubset(game["unlockedCharacters"])

        # 5. NPC 선택 및 대화 기록 API 조회
        selected = client.post(f"{path}/characters/C02/select")
        assert selected.status_code == 200

        history = client.get(f"{path}/chats/C02")
        assert history.status_code == 200
        assert history.json()["messages"] == []

        # 6. 첫 지목 실패
        revision = repository.load_state(sid).revision
        wrong = client.post(
            f"{path}/accusations",
            json={
                "suspectId": "C02",
                "expectedRevision": revision,
            },
        )
        assert wrong.status_code == 200, wrong.text
        assert wrong.json()["result"] == "INCORRECT"
        assert wrong.json()["attemptsLeft"] == 2
        assert wrong.json()["game"]["phase"] == "INVESTIGATION"

        # 7. 오답 후 조사 재개 및 다른 NPC 선택
        retry_select = client.post(f"{path}/characters/C03/select")
        assert retry_select.status_code == 200

        # 8. 정답 지목 및 성공 엔딩
        revision = repository.load_state(sid).revision
        correct = client.post(
            f"{path}/accusations",
            json={
                "suspectId": "C03",
                "expectedRevision": revision,
            },
        )
        assert correct.status_code == 200, correct.text
        assert correct.json()["result"] == "CORRECT"
        assert correct.json()["game"]["phase"] == "FINISHED"

        ending = client.get(f"{path}/ending")
        assert ending.status_code == 200
        assert ending.json()["outcome"] == "SUCCESS"
        assert ending.json()["truth"]["perpetratorId"] == "C03"

        # 9. 게임 종료 후 재지목 차단
        revision = repository.load_state(sid).revision
        repeat = client.post(
            f"{path}/accusations",
            json={
                "suspectId": "C03",
                "expectedRevision": revision,
            },
        )
        assert repeat.status_code == 409

        # 10. 저장된 엔딩 상태 복구
        restored = client.get(path).json()
        assert restored["phase"] == "FINISHED"
        assert restored["outcome"] == "SUCCESS"
        assert restored["attemptsLeft"] == 1
