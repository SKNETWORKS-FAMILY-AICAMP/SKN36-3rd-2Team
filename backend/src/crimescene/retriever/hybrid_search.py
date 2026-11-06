"""Dense + Sparse + RRF 기반 Hybrid Search."""

from typing import Literal

from qdrant_client import QdrantClient

from crimescene.db.qdrant_collection import COLLECTION_NAME
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.dense_search import (
    search_dense_candidates,
)
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.rrf_fusion import (
    HybridSearchCandidate,
    fuse_rrf_candidates,
)
from crimescene.retriever.sparse_search import (
    search_sparse_candidates,
)

SourceType = Literal[
    "player_document",
    "npc_knowledge",
]

DEFAULT_CANDIDATE_K = 30
DEFAULT_TOP_K = 10
DEFAULT_RRF_K = 60


def search_hybrid_candidates(
    query: str,
    *,
    client: QdrantClient,
    embedder: OllamaEmbedder,
    encoder: KoreanBM25Encoder,
    source_type: SourceType,
    case_id: str = "CASE-001",
    character_id: str | None = None,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    top_k: int = DEFAULT_TOP_K,
    rrf_k: int = DEFAULT_RRF_K,
    collection_name: str = COLLECTION_NAME,
) -> list[HybridSearchCandidate]:
    """Dense와 BM25 검색 결과를 RRF로 결합한다.

    검색 결과는 접근 권한이 검증되지 않은 내부 후보이다.

    주의:
        GameState 기반 접근 제어를 수행하지 않는다.
        반환 결과를 플레이어나 LLM에 직접 전달하지 않는다.
    """

    # 1. 검색 질문 검증
    if not isinstance(query, str):
        raise TypeError("검색 질문은 문자열이어야 합니다.")

    if not query.strip():
        raise ValueError("검색 질문이 비어 있습니다.")

    query = query.strip()

    # 2. 사건 ID 및 컬렉션 이름 검증
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("유효한 사건 ID가 필요합니다.")

    if not isinstance(collection_name, str) or not collection_name.strip():
        raise ValueError("유효한 컬렉션 이름이 필요합니다.")

    # 3. 문서 유형 검증
    if source_type not in (
        "player_document",
        "npc_knowledge",
    ):
        raise ValueError("지원하지 않는 문서 유형입니다.")

    # 4. NPC 검색 조건 검증
    if source_type == "npc_knowledge":
        if not isinstance(character_id, str) or not character_id.strip():
            raise ValueError("NPC 검색에는 character_id가 필요합니다.")

    elif character_id is not None:
        raise ValueError("플레이어 문서 검색에는 character_id를 지정할 수 없습니다.")

    # 5. 후보 검색 개수 검증
    if isinstance(candidate_k, bool) or not isinstance(candidate_k, int):
        raise TypeError("candidate_k는 정수여야 합니다.")

    if not 1 <= candidate_k <= 100:
        raise ValueError("candidate_k는 1~100 사이여야 합니다.")

    # 6. 최종 반환 개수 검증
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k는 정수여야 합니다.")

    if not 1 <= top_k <= candidate_k:
        raise ValueError("top_k는 1 이상 candidate_k 이하여야 합니다.")

    # 7. RRF 설정 검증
    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int):
        raise TypeError("rrf_k는 정수여야 합니다.")

    if rrf_k <= 0:
        raise ValueError("rrf_k는 양수여야 합니다.")

    # 8. BGE-M3 Dense 검색
    dense_results = search_dense_candidates(
        query,
        client=client,
        embedder=embedder,
        source_type=source_type,
        case_id=case_id,
        character_id=character_id,
        top_k=candidate_k,
        collection_name=collection_name,
    )

    # 9. Kiwi + BM25 Sparse 검색
    sparse_results = search_sparse_candidates(
        query,
        client=client,
        encoder=encoder,
        source_type=source_type,
        case_id=case_id,
        character_id=character_id,
        top_k=candidate_k,
        collection_name=collection_name,
    )

    # 10. RRF 검색 결과 결합
    hybrid_results = fuse_rrf_candidates(
        dense_results,
        sparse_results,
        top_k=top_k,
        rrf_k=rrf_k,
    )

    return hybrid_results
