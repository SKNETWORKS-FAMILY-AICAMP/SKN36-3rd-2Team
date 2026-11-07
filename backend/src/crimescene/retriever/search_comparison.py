"""Dense / BM25 / Hybrid 검색 결과 비교 및 평가."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from qdrant_client import QdrantClient

from crimescene.db.qdrant_collection import COLLECTION_NAME
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.dense_search import (
    DenseSearchCandidate,
    search_dense_candidates,
)
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.retrieval_metrics import (
    evaluate_retrieval_ranking,
)
from crimescene.retriever.rrf_fusion import (
    HybridSearchCandidate,
    fuse_rrf_candidates,
)
from crimescene.retriever.sparse_search import (
    SparseSearchCandidate,
    search_sparse_candidates,
)

SourceType = Literal["player_document", "npc_knowledge"]


@dataclass(frozen=True, slots=True)
class SearchComparisonResult:
    """권한 검증 전 검색 결과 비교 데이터."""

    query: str
    dense: tuple[DenseSearchCandidate, ...]
    sparse: tuple[SparseSearchCandidate, ...]
    hybrid: tuple[HybridSearchCandidate, ...]

    @property
    def overlap_ids(self) -> tuple[str, ...]:
        """Dense와 BM25가 공통으로 검색한 UUID."""

        dense_ids = {item.point_id for item in self.dense}
        sparse_ids = {item.point_id for item in self.sparse}

        return tuple(sorted(dense_ids & sparse_ids))

    @property
    def overlap_count(self) -> int:
        return len(self.overlap_ids)


def compare_search_methods(
    query: str,
    *,
    client: QdrantClient,
    embedder: OllamaEmbedder,
    encoder: KoreanBM25Encoder,
    source_type: SourceType = "player_document",
    case_id: str = "CASE-001",
    character_id: str | None = None,
    candidate_k: int = 30,
    top_k: int = 10,
    rrf_k: int = 60,
    collection_name: str = COLLECTION_NAME,
) -> SearchComparisonResult:
    """동일 질문에 대한 Dense, BM25, Hybrid 결과를 비교한다.

    세 검색 방식의 후보 UUID와 점수만 반환한다.

    접근 권한을 승인하지 않으므로 결과를 플레이어나
    LLM에 직접 전달해서는 안 된다.
    """

    if not isinstance(query, str):
        raise TypeError("검색 질문은 문자열이어야 합니다.")

    query = query.strip()

    if not query:
        raise ValueError("검색 질문이 비어 있습니다.")

    if (
        isinstance(candidate_k, bool)
        or not isinstance(candidate_k, int)
        or not 1 <= candidate_k <= 100
    ):
        raise ValueError("candidate_k는 1~100 사이여야 합니다.")

    if (
        isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or not 1 <= top_k <= candidate_k
    ):
        raise ValueError("top_k는 1 이상 candidate_k 이하여야 합니다.")

    # 두 검색 방식에 동일한 필터와 후보 개수 적용
    common = {
        "client": client,
        "source_type": source_type,
        "case_id": case_id,
        "character_id": character_id,
        "top_k": candidate_k,
        "collection_name": collection_name,
    }

    dense_results = search_dense_candidates(
        query,
        embedder=embedder,
        **common,
    )

    sparse_results = search_sparse_candidates(
        query,
        encoder=encoder,
        **common,
    )

    # 후보 전체를 사용해 RRF 순위 계산
    hybrid_results = fuse_rrf_candidates(
        dense_results,
        sparse_results,
        top_k=top_k,
        rrf_k=rrf_k,
    )

    return SearchComparisonResult(
        query=query,
        dense=tuple(dense_results[:top_k]),
        sparse=tuple(sparse_results[:top_k]),
        hybrid=tuple(hybrid_results),
    )


def evaluate_search_comparison(
    result: SearchComparisonResult,
    relevant_point_ids: Sequence[str],
) -> dict[str, dict[str, float]]:
    """정답 UUID를 기준으로 검색 방식별 지표를 계산한다.

    relevant_point_ids는 사람이 검증한 정답이어야 한다.
    검색 결과를 정답으로 자동 사용하지 않는다.
    """

    if not isinstance(result, SearchComparisonResult):
        raise TypeError("SearchComparisonResult가 필요합니다.")

    return {
        "dense": evaluate_retrieval_ranking(
            [item.point_id for item in result.dense],
            relevant_point_ids,
        ),
        "bm25": evaluate_retrieval_ranking(
            [item.point_id for item in result.sparse],
            relevant_point_ids,
        ),
        "hybrid": evaluate_retrieval_ranking(
            [item.point_id for item in result.hybrid],
            relevant_point_ids,
        ),
    }
