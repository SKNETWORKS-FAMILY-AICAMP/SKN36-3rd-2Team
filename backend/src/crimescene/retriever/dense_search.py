"""Qdrant Dense Vector 기반 RAG 검색 후보 조회."""

import logging
import math
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from qdrant_client import QdrantClient, models

from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
)
from crimescene.ingest.ollama_embedder import OllamaEmbedder

logger = logging.getLogger(__name__)

SourceType = Literal[
    "player_document",
    "npc_knowledge",
]


@dataclass(frozen=True, slots=True)
class DenseSearchCandidate:
    """접근 권한이 아직 검증되지 않은 검색 후보.

    본문과 접근 정책 메타데이터는 포함하지 않는다.
    """

    point_id: str
    score: float


def search_dense_candidates(
    query: str,
    *,
    client: QdrantClient,
    embedder: OllamaEmbedder,
    source_type: SourceType,
    case_id: str = "CASE-001",
    character_id: str | None = None,
    top_k: int = 10,
    collection_name: str = COLLECTION_NAME,
) -> list[DenseSearchCandidate]:
    """BGE-M3 임베딩으로 Qdrant 검색 후보를 조회한다.

    주의:
        이 함수는 검색만 수행한다.
        GameState 및 접근 정책에 따른 공개 권한을
        승인하지 않는다.

        반환된 후보를 플레이어나 LLM에 직접 전달해서는
        안 된다.
    """

    # 1. 질문 검증
    if not isinstance(query, str):
        raise TypeError("검색 질문은 문자열이어야 합니다.")

    if not query.strip():
        raise ValueError("검색 질문이 비어 있습니다.")

    # 2. 사건 ID 검증
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("유효한 사건 ID가 필요합니다.")

    # 3. 컬렉션 이름 검증
    if not isinstance(collection_name, str) or not collection_name.strip():
        raise ValueError("유효한 컬렉션 이름이 필요합니다.")

    # 4. 검색 개수 검증
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k는 정수여야 합니다.")

    if not 1 <= top_k <= 100:
        raise ValueError("top_k는 1~100 사이여야 합니다.")

    # 5. 문서 유형 검증
    if source_type not in (
        "player_document",
        "npc_knowledge",
    ):
        raise ValueError("지원하지 않는 문서 유형입니다.")

    # 6. NPC 검색 조건 검증
    if source_type == "npc_knowledge":
        if not isinstance(character_id, str) or not character_id.strip():
            raise ValueError("NPC 지식 검색에는 character_id가 필요합니다.")

    elif character_id is not None:
        raise ValueError("플레이어 문서 검색에는 character_id를 지정할 수 없습니다.")

    # 7. 질문 임베딩 생성 시간 측정
    embedding_started = perf_counter()

    query_vector = embedder.embed_query(query.strip())

    embedding_ms = (perf_counter() - embedding_started) * 1000

    # 8. 벡터 차원 및 유효성 검증
    if len(query_vector) != DENSE_VECTOR_SIZE:
        raise ValueError("질문 임베딩 차원이 일치하지 않습니다.")

    if not all(math.isfinite(value) for value in query_vector):
        raise ValueError("유효하지 않은 질문 임베딩입니다.")

    if not any(value != 0 for value in query_vector):
        raise ValueError("질문 임베딩이 영벡터입니다.")

    # 9. Qdrant 검색 필터 구성
    conditions = [
        models.FieldCondition(
            key="case_id",
            match=models.MatchValue(value=case_id),
        ),
        models.FieldCondition(
            key="source_type",
            match=models.MatchValue(value=source_type),
        ),
    ]

    if character_id is not None:
        conditions.append(
            models.FieldCondition(
                key="character_id",
                match=models.MatchValue(value=character_id),
            )
        )

    query_filter = models.Filter(must=conditions)

    # 10. Qdrant Dense Vector 검색 시간 측정
    qdrant_started = perf_counter()

    response = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        using=DENSE_VECTOR_NAME,
        query_filter=query_filter,
        limit=top_k,
        with_payload=False,
        with_vectors=False,
    )

    qdrant_ms = (perf_counter() - qdrant_started) * 1000

    if os.getenv("CRIMESCENE_PERF_LOG", "").lower() in {"1", "true", "yes"}:
        logger.warning(
            "NPC_DENSE_TIMING embedding_ms=%.2f qdrant_ms=%.2f",
            embedding_ms,
            qdrant_ms,
        )

    # 11. 검색 결과를 안전한 내부 후보 모델로 변환
    candidates = []

    for point in response.points:
        if not math.isfinite(point.score):
            raise ValueError("유효하지 않은 검색 점수가 반환되었습니다.")

        candidates.append(
            DenseSearchCandidate(
                point_id=str(point.id),
                score=float(point.score),
            )
        )

    return candidates
