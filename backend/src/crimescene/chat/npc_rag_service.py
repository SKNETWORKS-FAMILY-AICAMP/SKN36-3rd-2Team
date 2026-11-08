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
    allowed_entity_ids: tuple[str, ...] = ()
    known_relation_ids: tuple[str, ...] = ()
    known_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NPCChatRAGResult:
    """검색 및 접근 검증을 완료한 NPC 대화 준비 결과."""

    character_id: str
    history: tuple[NPCExchange, ...]
    reply_plan: NPCReplyPlan


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
        1. 세션의 현재 NPC 확인
        2. 페르소나 및 진술 규칙 구성
        3. 정책 제한 Hybrid RAG 검색
        4. Graph 검색 컨텍스트 확인
        5. 최종 응답 접근 검증
        6. 현재 NPC의 대화 이력만 반환

    이 함수는 LLM을 직접 호출하지 않는다.
    """

    question = _validate_query(query)

    if not isinstance(session_store, NPCSessionStore):
        raise TypeError("NPCSessionStore가 필요합니다.")

    if not isinstance(resources, NPCRAGResources):
        raise TypeError("NPCRAGResources가 필요합니다.")

    if isinstance(matched_topics, (str, bytes)):
        raise TypeError("질문 주제는 문자열 목록이어야 합니다.")

    topics = tuple(matched_topics)

    # 1. 서버 세션에서 현재 선택된 NPC를 가져온다.
    character_id = session_store.get_active_npc(state)

    if character_id is None:
        raise PermissionError("현재 대화 가능한 NPC가 없습니다.")

    # 2. 기본 말투만 포함하는 페르소나를 구성한다.
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

    # 3. 기존 #20 사전 접근 정책을 적용한 통합 검색.
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
        allowed_entity_ids=resources.allowed_entity_ids,
        matched_topics=topics,
        candidate_k=candidate_k,
        relation_top_k=relation_top_k,
        evidence_top_k=evidence_top_k,
    )

    # 4. Graph 후보가 있을 때만 후속 검증용 컨텍스트를 조회한다.
    # 현재 검색 API는 Graph 컨텍스트를 반환하지 않으므로,
    # 해당 경우 재조회한다. 추후 단일 조회로 최적화할 수 있다.
    if any(item.kind in {"relation", "evidence"} for item in candidates):
        graph_context = retrieve_question_graph(
            question,
            driver=resources.neo4j_driver,
            active_character_id=character_id,
            state=state,
            registry=resources.registry,
            trusted_edges=list(resources.trusted_edges),
            evidence_rules=resources.evidence_rules,
            allowed_entity_ids=resources.allowed_entity_ids,
            relation_top_k=relation_top_k,
            evidence_top_k=evidence_top_k,
        )

        if graph_context.character_id != character_id:
            raise ValueError("Graph 검색 대상 NPC가 일치하지 않습니다.")

        relation_ids = {relation.edge_id for relation in graph_context.relations}
        evidence_ids = {evidence.evidence_id for evidence in graph_context.evidence}

        # 두 조회 결과가 달라졌다면 근거 생성 전에 실패 처리한다.
        for candidate in candidates:
            if candidate.kind == "relation" and candidate.item_id not in relation_ids:
                raise ValueError("Graph 관계 후보가 일치하지 않습니다.")

            if candidate.kind == "evidence" and candidate.item_id not in evidence_ids:
                raise ValueError("Graph 증거 후보가 일치하지 않습니다.")

    else:
        graph_context = _empty_graph(character_id)

    # 검색 도중 NPC가 전환되었다면 결과를 폐기한다.
    if session_store.get_active_npc(state) != character_id:
        raise RuntimeError("검색 도중 NPC가 변경되었습니다.")

    # 5. 기존 #20 최종 접근 권한 검증을 재사용한다.
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
        allowed_entity_ids=resources.allowed_entity_ids,
        matched_topics=topics,
        top_k=top_k,
    )

    # 6. 다른 NPC로 전환되지 않았는지 다시 확인한다.
    if session_store.get_active_npc(state) != character_id:
        raise RuntimeError("검색 도중 NPC가 변경되었습니다.")

    history = session_store.get_history(
        state,
        character_id,
    )

    return NPCChatRAGResult(
        character_id=character_id,
        history=history,
        reply_plan=reply_plan,
    )
