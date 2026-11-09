"""Issue #23 - NPC 세션과 접근 제어 Hybrid RAG 검색 연결."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from neo4j import Driver
from qdrant_client import QdrantClient

from crimescene.chat.npc_behavior import build_npc_behavior_prompt
from crimescene.chat.npc_persona import NPCPersona
from crimescene.chat.npc_session import (
    MAX_MESSAGE_LENGTH,
    NPCExchange,
    NPCSessionStore,
)
from crimescene.chat.npc_social_style import build_social_personas
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.npc_presearch_access import (
    search_policy_scoped_multisource_candidates,
)
from crimescene.retriever.npc_response_gate import (
    NPCReplyPlan,
    prepare_npc_reply,
)
from crimescene.retriever.query_graph_retriever import (
    QuestionGraphContext,
    retrieve_question_graph,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

# ============================================================
# Constants
# ============================================================

# 게임 시작부터 공개된 엔티티
# V01: 신기범 (피해자)
PUBLIC_ENTITY_IDS = frozenset({"V01"})


# ============================================================
# RAG Resources
# ============================================================


@dataclass(frozen=True, slots=True, repr=False)
class NPCRAGResources:
    """서버에서 로딩한 신뢰 데이터와 검색 클라이언트."""

    personas: Mapping[str, NPCPersona]

    qdrant_client: QdrantClient
    neo4j_driver: Driver
    embedder: OllamaEmbedder
    encoder: KoreanBM25Encoder

    trusted_records: Sequence[HybridChunkRecord]
    documents: Sequence[PlayerDocument]
    npc_cards: Sequence[Mapping[str, object]]

    registry: Sequence[Mapping[str, object]]
    trusted_edges: Sequence[RelationshipSourceEdge]
    evidence_rules: Mapping[str, EvidenceRule]

    evaluator: PolicyEvaluator

    # 서버가 승인한 Graph 접근 권한만 전달한다.
    # 기본값은 기존 호출부와 호환되도록 유지한다.
    allowed_entity_ids: tuple[str, ...] = ()
    known_relation_ids: tuple[str, ...] = ()
    known_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NPCChatRAGResult:
    """검색 및 접근 검증을 완료한 NPC 대화 준비 결과."""

    character_id: str
    history: tuple[NPCExchange, ...]
    reply_plan: NPCReplyPlan


# ============================================================
# Validation
# ============================================================


def _validate_query(query: str) -> str:
    """플레이어 질문을 검증한다."""

    if not isinstance(query, str):
        raise TypeError("질문은 문자열이어야 합니다.")

    normalized = query.strip()

    if not normalized:
        raise ValueError("질문이 비어 있습니다.")

    if len(normalized) > MAX_MESSAGE_LENGTH:
        raise ValueError("질문 길이 제한을 초과했습니다.")

    return normalized


def _empty_graph(character_id: str) -> QuestionGraphContext:
    """Graph 후보가 없을 때 사용할 빈 컨텍스트."""

    return QuestionGraphContext(
        character_id=character_id,
        matched_entity_ids=(),
        relations=(),
        evidence=(),
    )


def _resolve_allowed_entity_ids(
    resources: NPCRAGResources,
) -> tuple[str, ...]:
    """기본 공개 엔티티와 서버 승인 엔티티를 통합한다.

    보안:
        - 공개 엔티티 V01만 기본 허용한다.
        - 다른 NPC의 해금 권한을 변경하지 않는다.
        - 증거 수집 및 공개 조건을 우회하지 않는다.
        - 실제 RAG 문서 접근 정책은 기존 엔진에서 검증한다.
    """

    if isinstance(resources.allowed_entity_ids, (str, bytes)):
        raise TypeError("허용 엔티티 목록 형식이 올바르지 않습니다.")

    allowed_ids = set(PUBLIC_ENTITY_IDS)

    for entity_id in resources.allowed_entity_ids:
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("유효하지 않은 엔티티 ID입니다.")

        allowed_ids.add(entity_id)

    return tuple(sorted(allowed_ids))


# ============================================================
# NPC Hybrid RAG
# ============================================================


def prepare_npc_chat_rag(
    query: str,
    *,
    state: GameState,
    session_store: NPCSessionStore,
    resources: NPCRAGResources,
    matched_topics: Iterable[str] = (),
    candidate_k: int = 30,
    relation_top_k: int = 20,
    evidence_top_k: int = 10,
    top_k: int = 10,
) -> NPCChatRAGResult:
    """현재 NPC에 한정된 Hybrid RAG 응답 계획을 생성한다.

    처리 순서:
        1. 입력값 및 세션 검증
        2. 공개 엔티티 접근 권한 구성
        3. NPC 페르소나 및 진술 규칙 구성
        4. 정책 제한 Hybrid RAG 검색
        5. Graph 검색 컨텍스트 검증
        6. 최종 RAG 접근 권한 검증
        7. 현재 NPC 대화 이력 반환

    이 함수는 LLM을 직접 호출하지 않는다.
    """

    # --------------------------------------------------------
    # 1. 입력값 검증
    # --------------------------------------------------------

    question = _validate_query(query)

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(session_store, NPCSessionStore):
        raise TypeError("NPCSessionStore가 필요합니다.")

    if not isinstance(resources, NPCRAGResources):
        raise TypeError("NPCRAGResources가 필요합니다.")

    if isinstance(matched_topics, (str, bytes)):
        raise TypeError("질문 주제는 문자열 목록이어야 합니다.")

    topics = tuple(matched_topics)

    # --------------------------------------------------------
    # 2. 공개 엔티티 접근 권한 구성
    # --------------------------------------------------------

    # 피해자 V01은 최초부터 질문할 수 있도록 허용한다.
    # 기존 서버 승인 엔티티 목록은 그대로 유지한다.
    allowed_entity_ids = _resolve_allowed_entity_ids(resources)

    # --------------------------------------------------------
    # 3. 현재 선택된 NPC 확인
    # --------------------------------------------------------

    character_id = session_store.get_active_npc(state)

    if character_id is None:
        raise PermissionError("현재 대화 가능한 NPC가 없습니다.")

    # --------------------------------------------------------
    # 4. NPC 페르소나 및 진술 규칙
    # --------------------------------------------------------

    social_personas = build_social_personas(
        resources.personas,
        active_character_id=character_id,
    )

    system_prompt = build_npc_behavior_prompt(
        social_personas,
        active_character_id=character_id,
        state=state,
        npc_cards=resources.npc_cards,
        evaluator=resources.evaluator,
        matched_topics=topics,
    )

    # --------------------------------------------------------
    # 5. Hybrid RAG 검색
    # --------------------------------------------------------

    candidates = search_policy_scoped_multisource_candidates(
        question,
        qdrant_client=resources.qdrant_client,
        neo4j_driver=resources.neo4j_driver,
        embedder=resources.embedder,
        encoder=resources.encoder,
        state=state,
        evaluator=resources.evaluator,
        active_character_id=character_id,
        trusted_records=resources.trusted_records,
        npc_cards=resources.npc_cards,
        registry=resources.registry,
        trusted_edges=list(resources.trusted_edges),
        evidence_rules=resources.evidence_rules,
        allowed_entity_ids=allowed_entity_ids,
        matched_topics=topics,
        candidate_k=candidate_k,
        relation_top_k=relation_top_k,
        evidence_top_k=evidence_top_k,
    )

    # --------------------------------------------------------
    # 6. Graph 검색 결과 검증
    # --------------------------------------------------------

    if any(item.kind in {"relation", "evidence"} for item in candidates):
        graph_context = retrieve_question_graph(
            question,
            driver=resources.neo4j_driver,
            active_character_id=character_id,
            state=state,
            registry=resources.registry,
            trusted_edges=list(resources.trusted_edges),
            evidence_rules=resources.evidence_rules,
            allowed_entity_ids=allowed_entity_ids,
            relation_top_k=relation_top_k,
            evidence_top_k=evidence_top_k,
        )

        if graph_context.character_id != character_id:
            raise ValueError("Graph 검색 대상 NPC가 일치하지 않습니다.")

        relation_ids = {relation.edge_id for relation in graph_context.relations}

        evidence_ids = {evidence.evidence_id for evidence in graph_context.evidence}

        # Graph 검색 결과가 변경되었다면 근거 생성 전에 차단한다.
        for candidate in candidates:
            if candidate.kind == "relation" and candidate.item_id not in relation_ids:
                raise ValueError("Graph 관계 후보가 일치하지 않습니다.")

            if candidate.kind == "evidence" and candidate.item_id not in evidence_ids:
                raise ValueError("Graph 증거 후보가 일치하지 않습니다.")

    else:
        graph_context = _empty_graph(character_id)

    # --------------------------------------------------------
    # 7. 검색 도중 NPC 변경 여부 확인
    # --------------------------------------------------------

    if session_store.get_active_npc(state) != character_id:
        raise RuntimeError("검색 도중 NPC가 변경되었습니다.")

    # --------------------------------------------------------
    # 8. 최종 RAG 접근 권한 검증
    # --------------------------------------------------------

    reply_plan = prepare_npc_reply(
        question,
        candidates=candidates,
        graph_context=graph_context,
        state=state,
        active_character_id=character_id,
        trusted_records=resources.trusted_records,
        documents=resources.documents,
        npc_cards=resources.npc_cards,
        registry=resources.registry,
        trusted_edges=resources.trusted_edges,
        evidence_rules=resources.evidence_rules,
        evaluator=resources.evaluator,
        npc_persona=system_prompt,
        known_relation_ids=resources.known_relation_ids,
        known_evidence_ids=resources.known_evidence_ids,
        allowed_entity_ids=allowed_entity_ids,
        matched_topics=topics,
        top_k=top_k,
    )

    # --------------------------------------------------------
    # 9. 최종 NPC 상태 검증
    # --------------------------------------------------------

    if session_store.get_active_npc(state) != character_id:
        raise RuntimeError("검색 도중 NPC가 변경되었습니다.")

    # --------------------------------------------------------
    # 10. 대화 이력 조회
    # --------------------------------------------------------

    history = session_store.get_history(
        state,
        character_id,
    )

    return NPCChatRAGResult(
        character_id=character_id,
        history=history,
        reply_plan=reply_plan,
    )
