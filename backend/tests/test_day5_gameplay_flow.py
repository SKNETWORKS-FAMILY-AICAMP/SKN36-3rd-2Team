"""Issue #148 - Day 5 대표 게임 플레이 API 통합 테스트."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import crimescene.trigger.case001_dialogue as dialogue_module
from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentType,
)
from crimescene.agents.deduction_agent import DeductionAgent
from crimescene.agents.orchestrator import AgentOrchestrator
from crimescene.agents.registry import AgentRegistry
from crimescene.api.app import create_app
from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    DjangoContentClient,
    PlayerScene,
)
from crimescene.api.story_event_conditions import StoryEventConditions
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.chapter_progress import ChapterUnlockRule
from crimescene.scenario.loaders.unlock_graph_loader import (
    Case001UnlockRules,
)
from crimescene.scenario.npc_unlock import NPCUnlockRule
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.story_context import StoryContextService
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository
from crimescene.trigger.npc_trigger import NPCTriggerRule


def make_policy(
    *,
    evidence=(),
    presentations=(),
):
    return AccessPolicy(
        required_evidence=list(evidence),
        required_presentations=list(presentations),
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character="C01",
    )


@pytest.fixture
def gameplay_runtime(tmp_path, monkeypatch):
    repository = SQLiteCase001Repository(
        tmp_path / "day5-gameplay.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="day5-gameplay-" + "x" * 40,
    )

    # 운영 시나리오와 무관한 테스트용 증거 및 점수입니다.
    scores = [1, 2, 3, 2, 3, 3, 2, 2, 1, 2]

    evidence_rules = {
        f"E{index:02d}": EvidenceRule(
            name=f"Test evidence {index}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for index, score in enumerate(scores, start=1)
    }

    policies = {
        "POL-COLLECT": make_policy(),
        "POL-TEST-REACTION": make_policy(
            evidence=("E01",),
            presentations=("C01:E01",),
        ),
    }

    evaluator = PolicyEvaluator(policies)

    # 실제 증거 제시 대상 계산에 사용되는 테스트 카드입니다.
    card = {
        **policies["POL-TEST-REACTION"].model_dump(),
        "id": "K-C01-01",
        "case_id": "CASE-001",
        "character_id": "C01",
        "policy_id": "POL-TEST-REACTION",
        "body": "Synthetic test statement",
        "access_scope": "character_only",
        "truth_status": "character_claim",
        "supersedes": [],
        "stage_priority": 1,
    }

    resources = NPCRAGResources(
        personas={},
        qdrant_client=None,
        neo4j_driver=None,
        embedder=None,
        encoder=None,
        trusted_records=(),
        documents=(),
        npc_cards=(card,),
        registry=(),
        trusted_edges=(),
        evidence_rules=evidence_rules,
        evaluator=evaluator,
    )

    app.state.dialogue_resources = resources
    app.state.dialogue_policies = policies

    app.state.acquisition_policy_ids = {
        evidence_id: "POL-COLLECT"
        for evidence_id in evidence_rules
    }

    app.state.acquisition_evaluator = evaluator
    app.state.django_evidence_gate_enabled = False

    # E01 획득으로 C02를 해금하고,
    # 검증된 증거 제시 및 질문으로 L01을 지급합니다.
    app.state.dialogue_flag_config = Case001UnlockRules(
        npc_rules={
            "C02": NPCUnlockRule(
                required_evidence=frozenset({"E01"}),
            )
        },
        flag_requirements={
            "L01": frozenset({"E01"}),
        },
        flag_sources={
            "L01": "C01 P:E01 & Q:verified_action",
        },
    )

    app.state.dialogue_triggers = (
        NPCTriggerRule(
            trigger_id="TRG-DAY5-REACTION",
            character_id="C01",
            policy_id="POL-TEST-REACTION",
            topic="verified_action",
            phrases=("verified action",),
        ),
    )

    app.state.chapter_unlock_rules = {
        "CH01": ChapterUnlockRule(
            target_chapter="CH01",
            required_evidence=frozenset({"E01"}),
            required_flags=frozenset({"L01"}),
            required_presentations=frozenset({"C01:E01"}),
        )
    }

    bindings = {}
    conditions = {}
    approved_events = {}

    for index, chapter in enumerate(
        ("CH00", "CH01"),
        start=1,
    ):
        story_id = f"STORY_{index:03d}"
        event_key = f"EVT-{chapter}-001"

        bindings[event_key] = StoryEventBinding(
            source_story_id=story_id,
            event_key=event_key,
            chapter=chapter,
        )

        conditions[story_id] = StoryEventConditions(
            story_id=story_id,
            chapter=chapter,
            all_evidence=frozenset({"E01"}),
            required_flags=frozenset({"L01"}),
        )

        approved_events[event_key] = ApprovedStoryEvent(
            event_key=event_key,
            chapter=chapter,
            trigger_type="EVIDENCE_COLLECTED",
            required_evidence_ids=["E01"],
            title=f"Test event {chapter}",
            text=f"Approved event {chapter}",
        )

    app.state.story_event_bindings = bindings
    app.state.story_event_conditions = conditions

    django = Mock(spec=DjangoContentClient)

    def get_event(case_id, event_key):
        assert case_id == "CASE-001"
        return approved_events[event_key]

    def get_scene(case_id, scene_id):
        assert case_id == "CASE-001"

        chapter = {
            "SC-0001": "CH00",
            "SC-0002": "CH01",
        }[scene_id]

        return PlayerScene(
            scene_id=scene_id,
            chapter=chapter,
            title=f"Test scene {chapter}",
            scene_text=f"Approved scene {chapter}",
        )

    django.get_approved_story_event.side_effect = get_event
    django.get_player_scene.side_effect = get_scene

    app.state.django_content_client = django

    # 반드시 테스트용 정답만 사용합니다.
    app.state.case_truth = CaseTruth(
        case_id="CASE-001",
        perpetrator_character_id="C02",
        motive="Synthetic motive",
        cause_of_death="Synthetic cause",
        crime_method="Synthetic method",
        crime_event_id="EVT-TEST",
    )

    def fake_npc_chat(
        question,
        *,
        state,
        session_store,
        resources,
        matched_topics,
        evidence_just_presented,
    ):
        # RAG 및 LLM 응답 생성만 대체합니다.
        # 증거 제시, Trigger, 플래그 판정은 실제 엔진이 실행합니다.
        character_id = session_store.get_active_npc(state)

        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )

        exchange = session_store.append_verified_exchange(
            state,
            character_id,
            user_message=question,
            reply=reply,
        )

        return NPCChatTurn(
            character_id=character_id,
            reply=reply,
            exchange=exchange,
            display_text=FALLBACK_REPLY,
        )

    monkeypatch.setattr(
        dialogue_module,
        "run_npc_chat",
        fake_npc_chat,
    )

    return app, repository, evidence_rules


def acknowledge_event(client, base, event_key):
    pending = client.get(
        f"{base}/story-events/pending"
    )

    assert pending.status_code == 200, pending.text

    assert [
        item["eventKey"]
        for item in pending.json()["items"]
    ] == [event_key]

    detail = client.get(
        f"{base}/story-events/{event_key}"
    )

    assert detail.status_code == 200

    first = client.post(
        f"{base}/story-events/{event_key}/ack"
    )

    assert first.status_code == 200, first.text
    assert first.json()["created"] is True

    repeated = client.post(
        f"{base}/story-events/{event_key}/ack"
    )

    assert repeated.status_code == 200
    assert repeated.json()["created"] is False

    assert repeated.json()["revision"] == (
        first.json()["revision"]
    )

    assert client.get(
        f"{base}/story-events/pending"
    ).json() == {"items": []}


@pytest.mark.parametrize(
    "expected_outcome",
    ["SUCCESS", "FAILURE"],
)
def test_day5_gameplay_from_prologue_to_ending(
    gameplay_runtime,
    tmp_path,
    expected_outcome,
):
    app, repository, evidence_rules = gameplay_runtime

    with TestClient(app) as client:
        # 1. 게임 생성
        created = client.post("/api/games")

        assert created.status_code == 201

        session_id = created.json()["sessionId"]
        base = f"/api/games/{session_id}"

        assert created.json()["phase"] == "PROLOGUE"
        assert created.json()["revision"] == 0

        # 엔딩은 게임 종료 전까지 공개하지 않습니다.
        assert client.get(
            f"{base}/ending"
        ).status_code == 409

        # 2. 프롤로그 장면 조회 및 완료
        scene = client.get(
            f"{base}/content/scenes/SC-0001"
        )

        assert scene.status_code == 200
        assert scene.json()["chapter"] == "CH00"

        assert client.get(
            f"{base}/content/scenes/SC-0002"
        ).status_code == 404

        started = client.post(
            f"{base}/prologue/complete"
        )

        assert started.status_code == 200
        assert started.json()["phase"] == "INVESTIGATION"

        # 3. NPC 선택 및 일반 대화
        selected = client.post(
            f"{base}/characters/C01/select"
        )

        assert selected.status_code == 200

        greeting = client.post(
            f"{base}/chat",
            json={"question": "Hello"},
        )

        assert greeting.status_code == 200, greeting.text

        # 미획득 증거 제시 차단
        before = repository.load_state(session_id)

        forbidden = client.post(
            f"{base}/chat",
            json={
                "question": "verified action",
                "presentedEvidenceId": "E01",
            },
        )

        assert forbidden.status_code == 403
        assert repository.load_state(session_id) == before

        # 4. 증거 E01 획득 및 NPC 해금
        collected = client.post(
            f"{base}/evidence/E01/collect"
        )

        assert collected.status_code == 200, collected.text
        assert collected.json()["created"] is True

        assert "C02" in collected.json()[
            "newlyUnlockedCharacters"
        ]

        saved = repository.load_state(session_id)

        assert saved.evidence["E01"].stage == "found"
        assert saved.score == 1
        assert saved.queued_story_events == []

        # 동일 증거 중복 획득은 상태를 변경하지 않습니다.
        duplicate = client.post(
            f"{base}/evidence/E01/collect"
        )

        assert duplicate.status_code == 200
        assert duplicate.json()["created"] is False
        assert repository.load_state(session_id) == saved

        # 증거와 플래그가 충분하지 않으면 챕터 전환 거부
        denied = client.post(
            f"{base}/chapter/advance",
            json={"expectedRevision": saved.revision},
        )

        assert denied.status_code == 409
        assert repository.load_state(session_id) == saved

        # 5. 실제 증거 제시 및 Trigger 실행
        presented = client.post(
            f"{base}/chat",
            json={
                "question": "verified action",
                "presentedEvidenceId": "E01",
            },
        )

        assert presented.status_code == 200, presented.text

        state = repository.load_state(session_id)

        assert state.presented["C01"] == ["E01"]
        assert "L01" in state.flags
        assert state.queued_story_events == ["STORY_001"]

        context = StoryContextService(repository).load(
            session_id,
            expected_revision=state.revision,
        )

        assert context.get_presented_evidence("C01") == (
            "E01",
        )

        # 6. CH00 이벤트 확인
        acknowledge_event(
            client,
            base,
            "EVT-CH00-001",
        )

        # 7. CH01 전환
        state = repository.load_state(session_id)

        advanced = client.post(
            f"{base}/chapter/advance",
            json={"expectedRevision": state.revision},
        )

        assert advanced.status_code == 200, advanced.text
        assert advanced.json()["currentChapter"] == "CH01"

        scene = client.get(
            f"{base}/content/scenes/SC-0002"
        )

        assert scene.status_code == 200
        assert scene.json()["chapter"] == "CH01"

        assert client.get(
            f"{base}/content/scenes/SC-0001"
        ).status_code == 404

        # 8. CH01 이벤트 확인
        acknowledge_event(
            client,
            base,
            "EVT-CH01-001",
        )

        # 9. 나머지 증거 획득
        for index in range(2, 6):
            evidence_id = f"E{index:02d}"

            result = client.post(
                f"{base}/evidence/{evidence_id}/collect"
            )

            assert result.status_code == 200, result.text
            assert result.json()["created"] is True

        ready = repository.load_state(session_id)

        assert len(ready.evidence) == 5
        assert ready.score == 11
        assert ready.attempts_left == 3

        assert ready.acknowledged_story_events == [
            "STORY_001",
            "STORY_002",
        ]

        resumed = client.get(base)

        assert resumed.status_code == 200
        assert resumed.json()["canAccuse"] is True

        # 10. SQLite 저장소 재개방
        reopened = SQLiteCase001Repository(
            tmp_path / "day5-gameplay.sqlite3"
        )

        assert reopened.load_state(session_id) == ready

        assert len(
            reopened.load_history(session_id, "C01")
        ) == 2

        # 11. 실제 Deduction Agent 실행
        orchestrator = AgentOrchestrator(
            AgentRegistry(
                [
                    DeductionAgent(
                        load_state=repository.load_state,
                        evidence_rules=evidence_rules,
                    )
                ]
            ),
            load_state=repository.load_state,
        )

        deduction = orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.DEDUCTION,
                message="Review E01 and E02.",
            ),
            context=AgentContext.from_game_state(
                ready,
                active_character_id="C01",
            ),
        )

        assert deduction.source_ids == ("E01", "E02")
        assert repository.load_state(session_id) == ready

        # 12. 서버 판정에 따라 서로 다른 엔딩 도달
        if expected_outcome == "SUCCESS":
            suspects = ["C02"]
            expected_result = "CORRECT"
        else:
            suspects = ["C01"] * 3
            expected_result = "INCORRECT"

        for suspect in suspects:
            current = repository.load_state(session_id)

            accused = client.post(
                f"{base}/accusations",
                json={
                    "suspectId": suspect,
                    "expectedRevision": current.revision,
                },
            )

            assert accused.status_code == 200, accused.text

            assert accused.json()["result"] == (
                expected_result
            )

        final = repository.load_state(session_id)

        assert final.phase.value == "FINISHED"
        assert final.outcome == expected_outcome

        # 13. 엔딩 공개 정책 검증
        ending = client.get(f"{base}/ending")

        assert ending.status_code == 200, ending.text
        assert ending.json()["outcome"] == expected_outcome

        if expected_outcome == "SUCCESS":
            assert ending.json()["truth"]["perpetratorId"] == (
                "C02"
            )
            assert final.attempts_left == 2
        else:
            assert ending.json().get("truth") is None
            assert final.attempts_left == 0

        # 종료된 게임의 상태 변경 차단
        assert client.post(
            f"{base}/chat",
            json={"question": "Hello"},
        ).status_code == 409

        assert client.post(
            f"{base}/evidence/E06/collect"
        ).status_code == 409

        assert client.post(
            f"{base}/chapter/advance",
            json={"expectedRevision": final.revision},
        ).status_code == 409

        assert repository.load_state(session_id) == final