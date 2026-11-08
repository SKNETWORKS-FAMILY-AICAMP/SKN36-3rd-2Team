"""Issue #24: CASE-001 NPC 증거 제시 전후 실제 Hybrid RAG 및 SQLite E2E."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from neo4j import GraphDatabase
from ollama import Client as OllamaClient
from qdrant_client import QdrantClient

from crimescene.chat.llm_client import generate_npc_json
from crimescene.chat.npc_persona import load_npc_personas
from crimescene.chat.npc_rag_service import NPCRAGResources, prepare_npc_chat_rag
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.db.neo4j_ingest import load_entity_registry
from crimescene.db.neo4j_sync import find_source
from crimescene.db.qdrant_collection import COLLECTION_NAME
from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
    load_npc_cards,
)
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.npc_output_guard import run_grounded_npc_response
from crimescene.retriever.npc_presearch_access import build_authorized_npc_point_ids
from crimescene.scenario.loaders.access_policy_loader import load_access_policies
from crimescene.scenario.loaders.document_loader import load_player_documents
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.scenario.loaders.relationship_loader import load_relationship_edges
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.settings import settings
from crimescene.trigger.atomic_dialogue import (
    SQLiteCase001Repository,
    run_case001_npc_dialogue_atomic,
)
from crimescene.trigger.case001_dialogue import build_case001_recipients
from crimescene.trigger.evidence_presentation import process_npc_dialogue_event
from crimescene.trigger.npc_trigger import NPCTriggerRule

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / ".local" / "case001_v7_1"
DB_PATH = ROOT / ".local" / "npc_sessions_issue24_e2e.sqlite3"


def find_data_dir() -> Path:
    """CASE-001 관리자 원본 경로가 유일한지 확인한다."""

    matches = list(DATA_ROOT.glob("*/data/characters.json"))

    if len(matches) != 1:
        raise FileNotFoundError("CASE-001 characters.json 경로가 유일하지 않습니다.")

    data_dir = matches[0].parent

    required_files = (
        "characters.json",
        "player_documents.jsonl",
        "npc_knowledge_cards.jsonl",
        "access_policies.json",
    )

    for filename in required_files:
        if not (data_dir / filename).is_file():
            raise FileNotFoundError(f"CASE-001 필수 파일 누락: {filename}")

    return data_dir


def make_resources(
    data_dir: Path,
    *,
    qdrant: QdrantClient,
    neo4j_driver,
    ollama_client: OllamaClient,
) -> NPCRAGResources:
    """기존 #23과 동일한 신뢰 원본 및 RAG 리소스를 사용한다."""

    personas = load_npc_personas(data_dir / "characters.json")

    cards = load_npc_cards(data_dir / "npc_knowledge_cards.jsonl")

    policies = load_access_policies(data_dir / "access_policies.json")

    documents = load_player_documents(data_dir / "player_documents.jsonl")

    records = load_case001_hybrid_records(data_dir)

    registry = load_entity_registry(find_source(DATA_ROOT, "entity_registry.json"))

    edges = load_relationship_edges(
        find_source(
            DATA_ROOT,
            "relationship_edges_source.json",
        )
    )

    evidence_rules = load_evidence_rules(find_source(DATA_ROOT, "evidence_rules.json"))

    # 실제 CASE-001 원본 무결성 검증
    counts = (
        len(personas),
        len(cards),
        len(policies),
        len(evidence_rules),
        len(records),
    )

    if counts != (10, 88, 153, 10, 116):
        raise ValueError(f"CASE-001 원본 개수 불일치: {counts}")

    print("[PASS] CASE-001 실제 데이터 로딩")
    print("  NPC: 10 / NPC Cards: 88 / Policies: 153")
    print("  Evidence: 10 / RAG Chunks: 116")

    # Qdrant 실제 적재 데이터 확인
    if not qdrant.collection_exists(COLLECTION_NAME):
        raise RuntimeError(f"Qdrant 컬렉션 누락: {COLLECTION_NAME}")

    point_count = qdrant.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count

    if point_count != len(records):
        raise ValueError(f"Qdrant 데이터 불일치: {point_count} != {len(records)}")

    print(f"[PASS] Qdrant 데이터 검증: {point_count}개")

    return NPCRAGResources(
        personas=personas,
        qdrant_client=qdrant,
        neo4j_driver=neo4j_driver,
        embedder=OllamaEmbedder(
            model="bge-m3",
            vector_size=1024,
            client=ollama_client,
        ),
        encoder=KoreanBM25Encoder(),
        trusted_records=tuple(records),
        documents=tuple(documents),
        npc_cards=tuple(cards),
        registry=tuple(registry),
        trusted_edges=tuple(edges),
        evidence_rules=evidence_rules,
        evaluator=PolicyEvaluator(policies),
    )


def load_rules(
    path: Path | None,
) -> tuple[NPCTriggerRule, ...]:
    """서버에서 관리하는 NPC 트리거 규칙을 로딩한다."""

    if path is None:
        return ()

    data = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(data, list):
        raise TypeError("트리거 규칙은 JSON 배열이어야 합니다.")

    rules = tuple(NPCTriggerRule.model_validate(item) for item in data)

    if len({rule.trigger_id for rule in rules}) != len(rules):
        raise ValueError("트리거 ID가 중복됐습니다.")

    return rules


def make_state(
    npc_id: str,
    evidence_id: str,
) -> GameState:
    """증거는 수집했지만 아직 NPC에게 제시하지 않은 초기 상태."""

    return GameState(
        case_id="CASE-001",
        session_id=f"ISSUE24-LIVE-{uuid4().hex}",
        unlocked_characters=[npc_id],
        evidence={evidence_id: EvidenceState(stage="found")},
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


def authorized_sources(
    *,
    state: GameState,
    npc: str,
    topics: tuple[str, ...],
    resources: NPCRAGResources,
) -> set[str]:
    """접근 정책에서 승인한 청크를 NPC 카드 ID로 변환한다."""

    point_ids = build_authorized_npc_point_ids(
        trusted_records=resources.trusted_records,
        npc_cards=resources.npc_cards,
        state=state,
        evaluator=resources.evaluator,
        active_character_id=npc,
        matched_topics=topics,
    )

    return {
        record.chunk.source_id
        for record in resources.trusted_records
        if record.chunk.point_id in point_ids
    }


def select_question_for_e2e(
    *,
    requested_question: str | None,
    npc: str,
    evidence_id: str,
    state: GameState,
    store: NPCSessionStore,
    resources: NPCRAGResources,
    recipients: dict[str, frozenset[str]],
    triggers: tuple[NPCTriggerRule, ...],
) -> str:
    """실제 Ollama가 신규 해금 카드를 인용할 수 있는 질문을 선택한다."""

    # 실제 사건 데이터에 맞춘 E2E 전용 질문입니다.
    # 운영 환경의 플레이어 질문에는 적용하지 않습니다.
    focused_questions = {
        ("C01", "E05"): (
            "그날 회의에서 언쟁이 있었다고 들었습니다. 왜 말이 높아졌나요?",
            "그날 회의에서 다툼이 있었나요? 당시 어떤 일이 있었나요?",
            "그날 서두르지 말자고 하셨다는데, 무슨 상황이었나요?",
        ),
    }

    if requested_question is not None:
        questions = [requested_question.strip()]
    else:
        questions = [
            *focused_questions.get((npc, evidence_id), ()),
            *resources.evidence_rules[evidence_id].q,
        ]

    questions = list(
        dict.fromkeys(
            text.strip() for text in questions if isinstance(text, str) and text.strip()
        )
    )

    if not questions:
        raise ValueError("검증할 질문이 없습니다.")

    for index, candidate in enumerate(questions, start=1):
        if len(candidate) > 4000:
            raise ValueError("질문 길이 제한을 초과했습니다.")

        # 1. 증거 제시 전 GameState
        before_event = process_npc_dialogue_event(
            candidate,
            state=state,
            active_character_id=npc,
            trigger_rules=triggers,
            evaluator=resources.evaluator,
            evidence_rules=resources.evidence_rules,
            allowed_recipients=recipients,
        )

        # 2. 증거 제시 후 GameState
        after_event = process_npc_dialogue_event(
            candidate,
            state=before_event.state,
            active_character_id=npc,
            trigger_rules=triggers,
            evaluator=resources.evaluator,
            evidence_rules=resources.evidence_rules,
            allowed_recipients=recipients,
            presented_evidence_id=evidence_id,
        )

        # 3. 증거 제시 전 승인된 NPC 카드
        before_sources = authorized_sources(
            state=before_event.state,
            npc=npc,
            topics=before_event.matched_topics,
            resources=resources,
        )

        # 4. 증거 제시 후 승인된 NPC 카드
        after_sources = authorized_sources(
            state=after_event.state,
            npc=npc,
            topics=after_event.matched_topics,
            resources=resources,
        )

        newly_unlocked = after_sources - before_sources

        if not newly_unlocked:
            print(f"[PROBE {index}] 새로 해금된 카드가 없습니다.")
            continue

        # 5. 실제 Hybrid RAG 검색
        rag_result = prepare_npc_chat_rag(
            candidate,
            state=after_event.state,
            session_store=store,
            resources=resources,
            matched_topics=after_event.matched_topics,
        )

        plan = rag_result.reply_plan

        retrieved = newly_unlocked.intersection(plan.source_ids)

        print()
        print(f"[PROBE {index}] 질문: {candidate}")
        print(f"  신규 해금: {sorted(newly_unlocked)}")
        print(f"  RAG 검색: {sorted(retrieved)}")
        print(f"  LLM 호출 가능: {plan.can_call_llm}")

        if not retrieved or not plan.can_call_llm:
            continue

        context = plan.authorized_context

        if context is None:
            continue

        # 6. 실제 Ollama 응답 생성 및 인용 검증
        #
        # DB에 기록하지 않는 사전 검증입니다.
        # 가짜 답변을 생성하거나 보안 정책을 우회하지 않습니다.
        reply = run_grounded_npc_response(
            plan,
            context,
            generate=generate_npc_json,
        )

        cited = newly_unlocked.intersection(reply.source_ids)

        print(f"  응답 검증: {reply.grounded}")
        print(f"  실제 인용: {reply.source_ids}")

        if not cited:
            print("  [SKIP] 신규 카드가 실제 답변에서 인용되지 않았습니다.")
            continue

        # 7. 실제 Ollama 검증까지 통과한 질문만 선택
        print()
        print("[PASS] 신규 카드 실제 인용 확인")
        print(f"[PASS] E2E 질문 선택: {candidate}")

        return candidate

    raise AssertionError(
        "모든 질문 후보에서 신규 NPC 카드의 "
        "실제 인용 검증에 실패했습니다. "
        "이 경우에는 Ollama 프롬프트 또는 "
        "NPC 출력 검증기를 추가 점검해야 합니다."
    )


def run(
    *,
    npc_id: str | None,
    evidence_id: str | None,
    question: str | None,
    embed_url: str,
    rules_path: Path | None,
) -> None:
    """증거 제시 전후 실제 RAG·Ollama·SQLite 결과를 검증한다."""

    # ----------------------------------------------
    # 1. 입력값 검증
    # ----------------------------------------------

    if (npc_id is None) != (evidence_id is None):
        raise ValueError("--npc와 --evidence는 함께 지정해야 합니다.")

    if not settings.ollama_model:
        raise ValueError("OLLAMA_MODEL 설정이 필요합니다.")

    # ----------------------------------------------
    # 2. 실제 CASE-001 원본 로딩
    # ----------------------------------------------

    data_dir = find_data_dir()

    policies = load_access_policies(data_dir / "access_policies.json")

    triggers = load_rules(rules_path)

    # ----------------------------------------------
    # 3. Qdrant 및 Neo4j 연결
    # ----------------------------------------------

    qdrant = QdrantClient(
        url=settings.qdrant_url,
        timeout=60,
    )

    try:
        with GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(
                settings.neo4j_user,
                settings.neo4j_password.get_secret_value(),
            ),
            connection_timeout=10,
        ) as neo4j:
            neo4j.verify_connectivity()

            print("[PASS] Neo4j 연결")

            # ------------------------------------------
            # 4. 실제 RAG 리소스 구성
            # ------------------------------------------

            resources = make_resources(
                data_dir,
                qdrant=qdrant,
                neo4j_driver=neo4j,
                ollama_client=OllamaClient(
                    host=embed_url,
                    timeout=600,
                ),
            )

            # ------------------------------------------
            # 5. 증거별 제시 가능 NPC 계산
            # ------------------------------------------

            recipients = build_case001_recipients(
                policies=policies,
                npc_cards=resources.npc_cards,
                evidence_rules=resources.evidence_rules,
            )

            valid_pairs = sorted(
                (npc, evidence) for evidence, npcs in recipients.items() for npc in npcs
            )

            if not valid_pairs:
                raise AssertionError("실제 접근 정책에 증거 제시 대상이 없습니다.")

            if npc_id is not None:
                pair = (npc_id, evidence_id)
            else:
                pair = valid_pairs[0]

            if pair not in valid_pairs:
                raise ValueError(f"허용되지 않은 증거 제시 조합입니다: {pair}")

            npc, evidence = pair

            # ------------------------------------------
            # 6. 초기 GameState 구성
            # ------------------------------------------

            state = make_state(
                npc,
                evidence,
            )

            repository = SQLiteCase001Repository(DB_PATH)

            NPCSessionStore(repository=repository).select_npc(
                state,
                npc,
            )

            repository.register_state(state)

            # ------------------------------------------
            # 7. RAG 검색 가능한 질문 자동 탐색
            # ------------------------------------------

            selected_question = select_question_for_e2e(
                requested_question=question,
                npc=npc,
                evidence_id=evidence,
                state=state,
                store=NPCSessionStore(repository=repository),
                resources=resources,
                recipients=recipients,
                triggers=triggers,
            )

            # ------------------------------------------
            # 8. 증거 제시 전 NPC 대화
            # ------------------------------------------

            before = run_case001_npc_dialogue_atomic(
                selected_question,
                session_id=state.session_id,
                repository=repository,
                resources=resources,
                policies=policies,
                trigger_rules=triggers,
            )

            # ------------------------------------------
            # 9. 증거 제시 후 NPC 대화
            # ------------------------------------------

            after = run_case001_npc_dialogue_atomic(
                selected_question,
                session_id=state.session_id,
                repository=repository,
                resources=resources,
                policies=policies,
                trigger_rules=triggers,
                presented_evidence_id=evidence,
            )

            # ------------------------------------------
            # 10. SQLite 재연결 및 영구 저장 검증
            # ------------------------------------------

            restarted = SQLiteCase001Repository(DB_PATH)

            persisted = restarted.load_state(state.session_id)

            history = restarted.load_history(
                state.session_id,
                npc,
            )

            if persisted != after.state or len(history) != 2:
                raise AssertionError("GameState 또는 NPC 대화 기록 복원 실패")

            if not after.presentation_created:
                raise AssertionError("증거 제시 기록이 생성되지 않았습니다.")

            if evidence not in persisted.presented.get(
                npc,
                (),
            ):
                raise AssertionError("증거 제시 기록이 저장되지 않았습니다.")

            if (history[0], history[1]) != (
                before.turn.exchange,
                after.turn.exchange,
            ):
                raise AssertionError("복원된 NPC 대화 내용이 일치하지 않습니다.")

            # ------------------------------------------
            # 11. 증거 제시 전후 승인된 정보 비교
            # ------------------------------------------

            before_topics = tuple(
                rule.topic for rule in triggers if rule.trigger_id in before.trigger_ids
            )

            after_topics = tuple(
                rule.topic for rule in triggers if rule.trigger_id in after.trigger_ids
            )

            before_sources = authorized_sources(
                state=before.state,
                npc=npc,
                topics=before_topics,
                resources=resources,
            )

            after_sources = authorized_sources(
                state=after.state,
                npc=npc,
                topics=after_topics,
                resources=resources,
            )

            # 이번 증거 제시로 새롭게 승인된 정보
            unlocked_sources = after_sources - before_sources

            # 새롭게 공개 가능한 실제 NPC 카드의 내용을 확인한다.
            # 개발용 E2E 진단에서만 출력하며 운영 API에는 노출하지 않는다.
            for record in resources.trusted_records:
                chunk = record.chunk

                if chunk.source_id not in unlocked_sources:
                    continue

                print()
                print("=" * 60)
                print("NEWLY UNLOCKED NPC KNOWLEDGE")
                print("=" * 60)

                print(f"NPC: {chunk.character_id}")
                print(f"Card ID: {chunk.source_id}")

            # 실제 NPC 답변에서 인용된 신규 정보
            cited_new_sources = unlocked_sources.intersection(
                after.turn.reply.source_ids
            )

            # ------------------------------------------
            # 12. 검증 결과 출력
            # ------------------------------------------

            print(f"[PASS] 연결 및 영구 저장: {npc}, {evidence}")

            print(f"[INFO] 트리거 수: {len(triggers)} / 발생: {after.trigger_ids}")

            print(f"[INFO] 이전 출처: {before.turn.reply.source_ids}")

            print(f"[INFO] 이후 출처: {after.turn.reply.source_ids}")

            print(f"[INFO] 새로 승인된 NPC 카드: {len(unlocked_sources)}개")

            print(f"[INFO] 이전 답변:\n{before.turn.reply.text}")

            print(f"[INFO] 이후 답변:\n{after.turn.reply.text}")

            # ------------------------------------------
            # 13. 비인가 정보 공개 검사
            # ------------------------------------------

            if not unlocked_sources:
                raise AssertionError("증거 제시 후 새로 승인된 NPC 카드가 없습니다.")

            if unlocked_sources.intersection(before.turn.reply.source_ids):
                raise AssertionError("증거 제시 이전에 비공개 NPC 카드가 인용됐습니다.")

            # ------------------------------------------
            # 14. 실제 답변에 신규 카드 반영 여부
            # ------------------------------------------

            if not cited_new_sources:
                # 검색 실패인지 LLM 인용 실패인지 진단한다.
                diagnostic = prepare_npc_chat_rag(
                    selected_question,
                    state=after.state,
                    session_store=NPCSessionStore(repository=restarted),
                    resources=resources,
                    matched_topics=after_topics,
                )

                plan = diagnostic.reply_plan

                retrieved = unlocked_sources.intersection(plan.source_ids)

                print()
                print("=" * 60)
                print("ISSUE #24 - RESPONSE DIAGNOSTICS")
                print("=" * 60)

                print(
                    "[DIAG] 새 카드 실제 검색:",
                    tuple(sorted(retrieved)),
                )

                print(
                    "[DIAG] LLM 호출 가능:",
                    plan.can_call_llm,
                )

                print(
                    "[DIAG] 근거 출처 수:",
                    len(plan.source_ids),
                )

                print(
                    "[DIAG] 실제 응답 grounded:",
                    after.turn.reply.grounded,
                )

                # RAG 검색 단계 실패
                if not retrieved:
                    raise AssertionError(
                        "새 카드는 해금됐지만 실제 RAG 근거에 없습니다."
                    )

                # Ollama 또는 JSON 인용 검증 단계 실패
                raise AssertionError(
                    "새 카드가 RAG 근거에 있으나 "
                    "검증된 답변에서 인용되지 않았습니다. "
                    "Ollama JSON 인용 형식과 "
                    "원문 일치 검증을 확인하세요."
                )

            print("[PASS] 새로 해금된 NPC 카드가 실제 검증 답변에 인용됐습니다.")

    finally:
        qdrant.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--npc")
    parser.add_argument("--evidence")
    parser.add_argument("--question")

    parser.add_argument(
        "--embed-url",
        default="http://127.0.0.1:11435",
    )

    parser.add_argument(
        "--rules",
        type=Path,
    )

    args = parser.parse_args()

    run(
        npc_id=args.npc,
        evidence_id=args.evidence,
        question=args.question,
        embed_url=args.embed_url,
        rules_path=args.rules,
    )
