"""Issue #23 - 실제 CASE-001 NPC RAG 대화 E2E 검증.

실제 Qdrant, Neo4j, Ollama, SQLite를 연결한다.

실행 모드:
    기본 실행:
        RAG 검색 및 접근 정책 검증

    --generate:
        Ollama 응답 생성, 출력 검증 및 SQLite 저장

    --generate --conversation:
        NPC 연속 대화, NPC 전환, 대화 이력 분리 및 복원 검증

주의:
    개발 환경 전용 E2E 스크립트다.
    실제 게임 엔진의 GameState를 대체하지 않는다.
"""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from neo4j import GraphDatabase
from ollama import Client as OllamaClient
from qdrant_client import QdrantClient

from crimescene.chat.llm_client import generate_npc_json
from crimescene.chat.npc_chat_runtime import run_npc_chat
from crimescene.chat.npc_persona import (
    EXPECTED_CHARACTER_IDS,
    load_npc_personas,
)
from crimescene.chat.npc_rag_service import (
    NPCRAGResources,
    prepare_npc_chat_rag,
)
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.chat.npc_session_repository import (
    SQLiteNPCSessionRepository,
)
from crimescene.db.neo4j_ingest import load_entity_registry
from crimescene.db.neo4j_sync import find_source
from crimescene.db.qdrant_collection import COLLECTION_NAME
from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
    load_npc_cards,
)
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)
from crimescene.scenario.loaders.evidence_loader import (
    load_evidence_rules,
)
from crimescene.scenario.loaders.relationship_loader import (
    load_relationship_edges,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GameState
from crimescene.settings import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / ".local" / "case001_v7_1"
DB_PATH = PROJECT_ROOT / ".local" / "npc_sessions_issue23.sqlite3"


# ============================================================
# 1. CASE-001 데이터 경로 확인
# ============================================================


def find_data_dir() -> Path:
    """실제 CASE-001 원본 데이터 경로를 확인한다."""

    matches = list(DATA_ROOT.glob("*/data/characters.json"))

    if len(matches) != 1:
        raise FileNotFoundError("CASE-001 characters.json 경로를 확인하세요.")

    data_dir = matches[0].parent

    required_files = (
        "characters.json",
        "player_documents.jsonl",
        "npc_knowledge_cards.jsonl",
        "access_policies.json",
    )

    for filename in required_files:
        if not (data_dir / filename).is_file():
            raise FileNotFoundError(f"필수 데이터가 없습니다: {filename}")

    return data_dir


# ============================================================
# 2. E2E 테스트용 GameState
# ============================================================


def make_test_state(character_id: str) -> GameState:
    """증거 미수집 상태의 E2E 전용 게임 세션을 생성한다."""

    if character_id not in EXPECTED_CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    return GameState(
        case_id="CASE-001",
        session_id=f"ISSUE23-E2E-{uuid4().hex}",
        unlocked_characters=[character_id],
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


# ============================================================
# 3. 실제 RAG 리소스 생성
# ============================================================


def make_resources(
    data_dir: Path,
    *,
    qdrant: QdrantClient,
    neo4j_driver,
    ollama_client: OllamaClient,
) -> NPCRAGResources:
    """CASE-001 원본과 실제 검색 엔진을 연결한다."""

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

    evidence_rules = load_evidence_rules(
        find_source(
            DATA_ROOT,
            "evidence_rules.json",
        )
    )

    print("[PASS] CASE-001 원본 로딩")
    print(f"  NPC: {len(personas)}")
    print(f"  NPC cards: {len(cards)}")
    print(f"  Policies: {len(policies)}")
    print(f"  Documents: {len(documents)}")
    print(f"  RAG chunks: {len(records)}")

    if len(personas) != 10:
        raise ValueError("NPC 개수가 올바르지 않습니다.")

    if len(cards) != 88:
        raise ValueError("NPC 카드 개수가 올바르지 않습니다.")

    if len(policies) != 153:
        raise ValueError("접근 정책 개수가 올바르지 않습니다.")

    # 실제 Qdrant 데이터와 서버 신뢰 원본을 비교한다.
    if not qdrant.collection_exists(COLLECTION_NAME):
        raise RuntimeError(f"Qdrant 컬렉션이 없습니다: {COLLECTION_NAME}")

    point_count = qdrant.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count

    print(f"[INFO] Qdrant points: {point_count}")

    if point_count != len(records):
        raise ValueError("Qdrant 데이터 수와 신뢰 원본 수가 일치하지 않습니다.")

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


# ============================================================
# 4. LLM 입력 및 NPC 대화 기억 검증
# ============================================================


def make_checked_generate(
    expected_questions: tuple[str, ...],
    call_state: dict[str, bool],
):
    """현재 NPC의 이전 대화만 전달됐는지 검사하는 LLM 호출 함수.

    콜백을 반복문 밖에서 생성하여 Ruff B023 문제를 방지한다.
    """

    def checked_generate(
        messages: list[dict[str, str]],
    ) -> str:
        call_state["called"] = True

        if not isinstance(messages, list):
            raise TypeError("LLM 메시지는 리스트여야 합니다.")

        if len(messages) != 2:
            raise ValueError("시스템 및 사용자 메시지가 필요합니다.")

        user_message = messages[1]

        if user_message.get("role") != "user":
            raise ValueError("LLM 사용자 메시지 역할이 올바르지 않습니다.")

        content = user_message.get("content")

        if not isinstance(content, str):
            raise TypeError("LLM 사용자 메시지는 문자열이어야 합니다.")

        payload = json.loads(content)

        if not isinstance(payload, dict):
            raise TypeError("LLM 입력 형식이 올바르지 않습니다.")

        # 현재 승인된 RAG 근거가 유지되는지 확인
        verified_context = payload.get("verified_context")

        if not isinstance(verified_context, str) or not verified_context.strip():
            raise ValueError("검증된 RAG 컨텍스트가 없습니다.")

        conversation_history = payload.get(
            "conversation_history",
            [],
        )

        if not isinstance(conversation_history, list):
            raise TypeError("conversation_history는 리스트여야 합니다.")

        actual_questions = []

        for entry in conversation_history:
            if not isinstance(entry, dict):
                raise TypeError("대화 기록 항목은 딕셔너리여야 합니다.")

            question = entry.get("player_question")

            if not isinstance(question, str):
                raise TypeError("이전 질문은 문자열이어야 합니다.")

            actual_questions.append(question)

        # 현재 NPC의 기록과 실제 LLM 입력을 비교한다.
        if tuple(actual_questions) != expected_questions:
            raise AssertionError(
                "다른 NPC의 대화 기록이 혼입됐거나 이전 대화가 누락됐습니다."
            )

        return generate_npc_json(messages)

    return checked_generate


# ============================================================
# 5. NPC 연속 대화 및 전환 E2E
# ============================================================


def evaluate_conversation(
    *,
    state: GameState,
    store: NPCSessionStore,
    resources: NPCRAGResources,
    first_npc: str,
) -> None:
    """NPC별 대화 기록과 컨텍스트 격리를 검증한다."""

    second_npc = "C02" if first_npc != "C02" else "C01"

    scenarios = [
        (
            first_npc,
            "그날 학교에서 무엇을 확인하셨나요?",
            0,
        ),
        (
            first_npc,
            "그날 학교에서 무엇을 확인하셨나요?",
            1,
        ),
        (
            second_npc,
            "학교 기록에 대해 아시는 게 있나요?",
            0,
        ),
        (
            first_npc,
            "그날 학교에서 무엇을 확인하셨나요?",
            2,
        ),
    ]

    print()
    print("=" * 65)
    print("NPC MULTI-TURN E2E")
    print("=" * 65)

    llm_checked_npcs: set[str] = set()

    for index, (npc_id, question, expected_count) in enumerate(
        scenarios,
        start=1,
    ):
        # 현재 대화 NPC 선택
        store.select_npc(
            state,
            npc_id,
        )

        previous_history = store.get_history(
            state,
            npc_id,
        )

        if len(previous_history) != expected_count:
            raise AssertionError(
                f"{npc_id} 이전 대화 개수 불일치: "
                f"{len(previous_history)} != {expected_count}"
            )

        # 반복마다 예상 대화 기록을 독립적으로 생성한다.
        expected_questions = tuple(
            exchange.user_message[:400] for exchange in previous_history[-4:]
        )

        # 반복마다 별도의 호출 상태를 사용한다.
        call_state = {"called": False}

        checked_generate = make_checked_generate(
            expected_questions,
            call_state,
        )

        print()
        print(f"[TURN {index}] NPC={npc_id}")

        turn = run_npc_chat(
            question,
            state=state,
            session_store=store,
            resources=resources,
            generate=checked_generate,
        )

        # 현재 NPC의 기록만 조회한다.
        current_history = store.get_history(
            state,
            npc_id,
        )

        if len(current_history) != expected_count + 1:
            raise AssertionError("대화 기록 저장 개수가 일치하지 않습니다.")

        if current_history[-1] != turn.exchange:
            raise AssertionError("최신 대화 저장 결과가 일치하지 않습니다.")

        llm_called = call_state["called"]

        print(f"  Grounded: {turn.reply.grounded}")
        print(f"  LLM called: {llm_called}")
        print(f"  History: {len(current_history)}")
        print(f"  Sources: {len(turn.reply.source_ids)}")

        if llm_called:
            llm_checked_npcs.add(npc_id)

        # 첫 NPC의 후속 질문에서는 실제 컨텍스트 전달을 확인한다.
        if npc_id == first_npc and expected_count > 0 and not llm_called:
            raise AssertionError(
                "후속 질문에 승인된 RAG 근거가 없어 "
                "LLM 대화 컨텍스트를 검증하지 못했습니다."
            )

        if npc_id == second_npc and not llm_called:
            print(
                "  [INFO] 두 번째 NPC의 승인된 근거가 없어 LLM이 호출되지 않았습니다."
            )

    # ========================================================
    # SQLite 재연결 후 기록 복원 검증
    # ========================================================

    restarted = NPCSessionStore(
        repository=SQLiteNPCSessionRepository(DB_PATH),
    )

    first_history = restarted.get_history(
        state,
        first_npc,
    )

    second_history = restarted.get_history(
        state,
        second_npc,
    )

    if len(first_history) != 3:
        raise AssertionError("첫 번째 NPC의 기록 복원에 실패했습니다.")

    if len(second_history) != 1:
        raise AssertionError("두 번째 NPC의 기록 복원에 실패했습니다.")

    if restarted.get_active_npc(state) != first_npc:
        raise AssertionError("NPC 선택 상태 복원에 실패했습니다.")

    print()
    print("=" * 65)
    print("NPC MULTI-TURN E2E RESULT")
    print("=" * 65)

    print(f"[PASS] {first_npc}: 대화 기록 3개 복원")

    print(f"[PASS] {second_npc}: 대화 기록 1개 복원")

    print("[PASS] NPC 전환 후 선택 상태 복원")

    print("[PASS] NPC별 대화 기록 분리")

    print("[PASS] SQLite 영구 저장")

    if second_npc not in llm_checked_npcs:
        print("[INFO] 두 번째 NPC의 실제 LLM 입력 격리는 아직 검증되지 않았습니다.")


# ============================================================
# 6. 실제 CASE-001 E2E 실행
# ============================================================


def evaluate(
    *,
    character_id: str,
    question: str,
    generate: bool,
    embed_url: str,
    conversation: bool = False,
) -> None:
    """실제 RAG 검색 및 선택한 E2E 시나리오를 실행한다."""

    if not isinstance(question, str):
        raise TypeError("질문은 문자열이어야 합니다.")

    if not question.strip():
        raise ValueError("질문이 비어 있습니다.")

    if generate and not settings.ollama_model:
        raise ValueError("실제 응답 생성에는 OLLAMA_MODEL 설정이 필요합니다.")

    if conversation and not generate:
        raise ValueError("연속 대화 검증에는 --generate 옵션이 필요합니다.")

    data_dir = find_data_dir()

    state = make_test_state(character_id)

    if conversation:
        second_npc = "C02" if character_id != "C02" else "C01"

        # E2E 테스트에서만 두 인물을 해금한다.
        state.unlocked_characters = [
            character_id,
            second_npc,
        ]

    repository = SQLiteNPCSessionRepository(DB_PATH)

    store = NPCSessionStore(
        repository=repository,
    )

    store.select_npc(
        state,
        character_id,
    )

    print("=" * 65)
    print("ISSUE #23 - NPC RAG E2E")
    print("=" * 65)

    print(f"NPC: {character_id}")
    print(f"Question: {question}")

    mode = (
        "CONVERSATION" if conversation else ("GENERATE" if generate else "SEARCH ONLY")
    )

    print(f"Mode: {mode}")

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
        ) as neo4j_driver:
            neo4j_driver.verify_connectivity()

            print("[PASS] Neo4j 연결")

            ollama_client = OllamaClient(
                host=embed_url,
                timeout=600,
            )

            # 실제 CASE-001 원본 데이터 로딩
            resources = make_resources(
                data_dir,
                qdrant=qdrant,
                neo4j_driver=neo4j_driver,
                ollama_client=ollama_client,
            )

            # NPC 전환 및 연속 대화 검증
            if conversation:
                evaluate_conversation(
                    state=state,
                    store=store,
                    resources=resources,
                    first_npc=character_id,
                )
                return

            print()
            print("[STEP] NPC Hybrid RAG 검색")

            # =================================================
            # 검색 전용 모드
            # =================================================

            if not generate:
                result = prepare_npc_chat_rag(
                    question,
                    state=state,
                    session_store=store,
                    resources=resources,
                )

                plan = result.reply_plan

                print("[PASS] RAG 검색 파이프라인 실행")

                print(f"  NPC: {result.character_id}")

                print(f"  LLM 호출 가능: {plan.can_call_llm}")

                print(f"  승인된 출처 수: {len(plan.source_ids)}")

                if not plan.can_call_llm:
                    print(
                        "[INFO] 현재 GameState에서 공개 가능한 "
                        "검색 근거가 없을 수 있습니다."
                    )

                print("[INFO] Ollama 답변 생성은 실행하지 않았습니다.")

                return

            # =================================================
            # 실제 Ollama 응답 생성 및 검증
            # =================================================

            print("[STEP] Ollama 응답 생성 및 검증")

            turn = run_npc_chat(
                question,
                state=state,
                session_store=store,
                resources=resources,
            )

            print("[PASS] NPC 응답 처리")

            print(f"  NPC: {turn.character_id}")

            print(f"  Grounded: {turn.reply.grounded}")

            print(f"  승인된 출처 수: {len(turn.reply.source_ids)}")

            print()
            print("[NPC RESPONSE]")
            print(turn.reply.text)

            # =================================================
            # SQLite 영구 저장 및 재조회 검증
            # =================================================

            restarted = NPCSessionStore(
                repository=SQLiteNPCSessionRepository(DB_PATH),
            )

            history = restarted.get_history(
                state,
                character_id,
            )

            if len(history) != 1:
                raise RuntimeError("SQLite 대화 기록 복원에 실패했습니다.")

            if history[0] != turn.exchange:
                raise RuntimeError("복원된 대화 기록이 원본과 일치하지 않습니다.")

            print()
            print("[PASS] SQLite 기록 저장 및 재조회")

            print(f"  History: {len(history)}")
            print(f"  Session: {state.session_id}")

    finally:
        qdrant.close()


# ============================================================
# 7. CLI 실행
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="CASE-001 NPC RAG 실제 환경 E2E 검증")

    parser.add_argument(
        "--npc",
        choices=sorted(EXPECTED_CHARACTER_IDS),
        default="C01",
    )

    parser.add_argument(
        "--question",
        default="그날 학교에서 무엇을 확인하셨나요?",
    )

    parser.add_argument(
        "--generate",
        action="store_true",
        help="Ollama 응답 생성 및 SQLite 저장까지 실행",
    )

    parser.add_argument(
        "--embed-url",
        default=settings.ollama_base_url,
        help="BGE-M3 임베딩 Ollama 서버 주소",
    )

    parser.add_argument(
        "--conversation",
        action="store_true",
        help="NPC 전환 및 연속 대화 E2E 검증",
    )

    args = parser.parse_args()

    if args.conversation and not args.generate:
        parser.error("--conversation은 --generate와 함께 사용해야 합니다.")

    evaluate(
        character_id=args.npc,
        question=args.question,
        generate=args.generate,
        embed_url=args.embed_url,
        conversation=args.conversation,
    )


if __name__ == "__main__":
    main()
