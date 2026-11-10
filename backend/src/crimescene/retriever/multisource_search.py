"""CASE-001 Qdrant + Neo4j 통합 검색 실행기."""

import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from time import perf_counter

from neo4j import Driver
from qdrant_client import QdrantClient

from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.dense_search import search_dense_candidates
from crimescene.retriever.graph_search import CHARACTER_IDS
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.multisource_rrf import (
    FusedSearchCandidate,
    fuse_multisource_candidates,
)
from crimescene.retriever.query_entity_extractor import (
    InaccessibleEntityMentionError,
    extract_question_entities,
)
from crimescene.retriever.query_graph_retriever import (
    retrieve_question_graph,
)
from crimescene.retriever.sparse_search import search_sparse_candidates
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

CASE_ID = "CASE-001"

logger = logging.getLogger(__name__)


def _validate_limit(value: int, name: str) -> None:
    """검색 후보 개수를 검증한다."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}은 정수여야 합니다.")

    if not 1 <= value <= 100:
        raise ValueError(f"{name}은 1~100 사이여야 합니다.")


def search_multisource_candidates(
    query: str,
    *,
    qdrant_client: QdrantClient,
    neo4j_driver: Driver,
    embedder: OllamaEmbedder,
    encoder: KoreanBM25Encoder,
    state: GameState,
    active_character_id: str,
    registry: Sequence[Mapping[str, object]],
    trusted_edges: list[RelationshipSourceEdge],
    evidence_rules: Mapping[str, EvidenceRule],
    trusted_point_ids: Iterable[str],
    allowed_entity_ids: Iterable[str] = (),
    candidate_k: int = 30,
    relation_top_k: int = 20,
    evidence_top_k: int = 10,
    rrf_k: int = 60,
) -> list[FusedSearchCandidate]:
    """NPC 대화용 Dense + BM25 + Graph 통합 후보 검색.

    이 함수는 세 검색 엔진을 연결하고 RRF 순위를 계산한다.

    중요:
        1. 현재 대화 NPC는 서버가 결정해야 한다.
        2. Qdrant 검색은 해당 NPC의 지식으로 제한한다.
        3. Graph 검색은 기존 GameState 권한 검증을 사용한다.
        4. Qdrant 결과 UUID는 신뢰 원본과 대조한다.
        5. 반환 후보는 LLM에 직접 전달하지 않는다.
        6. 문서 내용의 최종 접근 검증은 다음 단계에서 수행한다.
    """

    # --------------------------------------------------
    # 1. 입력값 검증
    # --------------------------------------------------

    if not isinstance(query, str):
        raise TypeError("검색 질문은 문자열이어야 합니다.")

    query = query.strip()

    if not query:
        raise ValueError("검색 질문이 비어 있습니다.")

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if (
        not isinstance(active_character_id, str)
        or active_character_id not in CHARACTER_IDS
    ):
        raise ValueError("유효하지 않은 NPC ID입니다.")

    _validate_limit(candidate_k, "candidate_k")
    _validate_limit(relation_top_k, "relation_top_k")
    _validate_limit(evidence_top_k, "evidence_top_k")

    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int):
        raise TypeError("rrf_k는 정수여야 합니다.")

    if rrf_k <= 0:
        raise ValueError("rrf_k는 양수여야 합니다.")

    if isinstance(allowed_entity_ids, (str, bytes)):
        raise TypeError("허용 엔티티 ID 목록이 올바르지 않습니다.")

    if isinstance(trusted_point_ids, (str, bytes)):
        raise TypeError("신뢰 UUID 목록이 올바르지 않습니다.")

    allowed_entities = set(allowed_entity_ids)
    trusted_ids = set(trusted_point_ids)

    if any(not isinstance(item, str) or not item.strip() for item in allowed_entities):
        raise ValueError("허용 엔티티 ID가 올바르지 않습니다.")

    if any(not isinstance(item, str) or not item.strip() for item in trusted_ids):
        raise ValueError("신뢰 UUID가 올바르지 않습니다.")

    # --------------------------------------------------
    # 2. 현재 대화 NPC 해금 여부
    # --------------------------------------------------

    if active_character_id not in state.unlocked_characters:
        return []

    # --------------------------------------------------
    # 3. 접근 불가능한 엔티티 질문 사전 차단
    # --------------------------------------------------

    search_started = perf_counter()

    try:
        extract_question_entities(
            query,
            registry=registry,
            state=state,
            evidence_rules=evidence_rules,
            allowed_entity_ids=allowed_entities,
            reject_inaccessible_mentions=True,
        )

    except InaccessibleEntityMentionError:
        # 잠긴 인물이나 미수집 증거를 명시적으로 질문하면
        # Qdrant와 Neo4j 모두 조회하지 않는다.
        return []

    # --------------------------------------------------
    # 4. Neo4j Graph Retrieval
    # --------------------------------------------------

    presearch_ms = (perf_counter() - search_started) * 1000
    graph_started = perf_counter()

    graph_context = retrieve_question_graph(
        query,
        driver=neo4j_driver,
        active_character_id=active_character_id,
        state=state,
        registry=registry,
        trusted_edges=trusted_edges,
        evidence_rules=evidence_rules,
        allowed_entity_ids=allowed_entities,
        relation_top_k=relation_top_k,
        evidence_top_k=evidence_top_k,
    )

    # --------------------------------------------------
    # 5. Qdrant Dense Search
    # --------------------------------------------------

    graph_ms = (perf_counter() - graph_started) * 1000
    dense_started = perf_counter()

    dense_results = search_dense_candidates(
        query,
        client=qdrant_client,
        embedder=embedder,
        source_type="npc_knowledge",
        case_id=state.case_id,
        character_id=active_character_id,
        top_k=candidate_k,
    )

    # --------------------------------------------------
    # 6. Qdrant BM25 Search
    # --------------------------------------------------

    dense_ms = (perf_counter() - dense_started) * 1000
    bm25_started = perf_counter()

    sparse_results = search_sparse_candidates(
        query,
        client=qdrant_client,
        encoder=encoder,
        source_type="npc_knowledge",
        case_id=state.case_id,
        character_id=active_character_id,
        top_k=candidate_k,
    )

    # --------------------------------------------------
    # 7. Qdrant UUID 신뢰 원본 검증
    # --------------------------------------------------

    bm25_ms = (perf_counter() - bm25_started) * 1000
    validation_started = perf_counter()

    for candidate in (*dense_results, *sparse_results):
        if candidate.point_id not in trusted_ids:
            raise ValueError("신뢰할 수 없는 Qdrant 검색 후보 UUID입니다.")

    validation_ms = (perf_counter() - validation_started) * 1000

    # --------------------------------------------------
    # 8. Dense + BM25 + Graph RRF 통합
    # --------------------------------------------------

    rrf_started = perf_counter()

    fused = fuse_multisource_candidates(
        dense_results,
        sparse_results,
        graph_context,
        top_k=None,
        rrf_k=rrf_k,
    )

    # 권한 검증 전 Top-K를 적용하지 않는다.
    # 다음 단계에서 최종 권한 검증 후 Top-K 선정.
    rrf_ms = (perf_counter() - rrf_started) * 1000

    if os.getenv("CRIMESCENE_PERF_LOG", "").lower() in {"1", "true", "yes"}:
        logger.warning(
            "NPC_RAG_TIMING "
            "presearch_ms=%.2f graph_ms=%.2f "
            "dense_ms=%.2f bm25_ms=%.2f "
            "validation_ms=%.2f rrf_ms=%.2f "
            "total_ms=%.2f candidate_k=%d result_count=%d",
            presearch_ms,
            graph_ms,
            dense_ms,
            bm25_ms,
            validation_ms,
            rrf_ms,
            (perf_counter() - search_started) * 1000,
            candidate_k,
            len(fused),
        )

    return fused
