"""Dense + BM25 + Neo4j Graph 기반 3중 RRF 검색 결과 통합."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from crimescene.retriever.dense_search import DenseSearchCandidate
from crimescene.retriever.graph_evidence_search import EvidenceGraphResult
from crimescene.retriever.graph_search import GraphSearchResult
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.retriever.sparse_search import SparseSearchCandidate

CandidateKind = Literal[
    "chunk",
    "relation",
    "evidence",
]

SearchMethod = Literal[
    "dense",
    "bm25",
    "graph",
]

DEFAULT_RRF_K = 60

METHOD_ORDER = (
    "dense",
    "bm25",
    "graph",
)


@dataclass(frozen=True, slots=True)
class FusedSearchCandidate:
    """접근 권한 검증 전 통합 검색 후보.

    kind:
        chunk    - Qdrant 문서 청크
        relation - Neo4j 관계
        evidence - Neo4j 증거 보유 관계

    item_id:
        chunk    - Qdrant point UUID
        relation - Neo4j edge_id
        evidence - 증거 ID

    methods:
        해당 후보를 반환한 검색 방식

    주의:
        이 모델은 내부 검색용입니다.
        LLM 또는 플레이어에게 직접 전달하면 안 됩니다.
    """

    kind: CandidateKind
    item_id: str
    score: float
    methods: tuple[SearchMethod, ...]


def _validate_limit(
    top_k: int | None,
    rrf_k: int,
) -> None:
    """RRF 검색 설정을 검증한다."""

    if top_k is not None:
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k는 정수여야 합니다.")

        if not 1 <= top_k <= 300:
            raise ValueError("top_k는 1~300 사이여야 합니다.")

    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int):
        raise TypeError("rrf_k는 정수여야 합니다.")

    if rrf_k <= 0:
        raise ValueError("rrf_k는 양수여야 합니다.")


def _validate_vector_candidates(
    candidates: Sequence,
    expected_type: type,
    method: str,
) -> list[str]:
    """Dense 또는 BM25 검색 결과의 UUID와 점수를 검증한다."""

    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise TypeError(f"{method} 검색 결과는 시퀀스여야 합니다.")

    ids = []
    seen = set()

    for candidate in candidates:
        if not isinstance(candidate, expected_type):
            raise TypeError(f"{method} 검색 후보 타입이 올바르지 않습니다.")

        point_id = candidate.point_id
        score = candidate.score

        if not isinstance(point_id, str) or not point_id.strip():
            raise ValueError("검색 후보 UUID가 올바르지 않습니다.")

        if point_id in seen:
            raise ValueError(f"중복된 검색 후보 UUID: {point_id}")

        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
        ):
            raise ValueError("유효하지 않은 검색 점수입니다.")

        seen.add(point_id)
        ids.append(point_id)

    return ids


def _validate_graph_candidates(
    graph: QuestionGraphContext,
) -> list[tuple[CandidateKind, str]]:
    """Graph Retrieval 결과를 공통 ID 구조로 변환한다."""

    if not isinstance(graph, QuestionGraphContext):
        raise TypeError("QuestionGraphContext가 필요합니다.")

    results = []
    seen = set()

    # 1. Neo4j 관계
    for relation in graph.relations:
        if not isinstance(relation, GraphSearchResult):
            raise TypeError("Graph 관계 후보 타입이 올바르지 않습니다.")

        edge_id = relation.edge_id

        if not isinstance(edge_id, str) or not edge_id.strip():
            raise ValueError("관계 ID가 올바르지 않습니다.")

        key = ("relation", edge_id)

        if key in seen:
            raise ValueError("중복된 Graph 관계 ID입니다.")

        seen.add(key)
        results.append(key)

    # 2. Neo4j 증거
    for evidence in graph.evidence:
        if not isinstance(evidence, EvidenceGraphResult):
            raise TypeError("Graph 증거 후보 타입이 올바르지 않습니다.")

        evidence_id = evidence.evidence_id

        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise ValueError("증거 ID가 올바르지 않습니다.")

        key = ("evidence", evidence_id)

        if key in seen:
            raise ValueError("중복된 Graph 증거 ID입니다.")

        seen.add(key)
        results.append(key)

    return results


def fuse_multisource_candidates(
    dense_candidates: Sequence[DenseSearchCandidate],
    sparse_candidates: Sequence[SparseSearchCandidate],
    graph_context: QuestionGraphContext,
    *,
    top_k: int | None = None,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[FusedSearchCandidate]:
    """Dense, BM25, Graph 검색 결과를 RRF로 결합한다.

    검색 순위만 사용하여 서로 다른 점수 체계를 정규화한다.

    동일한 Qdrant UUID:
        Dense와 BM25의 RRF 점수를 합산한다.

    서로 다른 데이터 종류:
        (kind, item_id) 조합으로 구분하여
        문서와 그래프 관계를 잘못 합치지 않는다.

    top_k=None:
        후보 전체를 반환한다.

    보안:
        이 함수는 최종 접근 권한을 승인하지 않는다.
        최종 LLM 컨텍스트 생성 전에 별도 권한 검사가 필요하다.
    """

    # --------------------------------------------------
    # 1. 입력값 검증
    # --------------------------------------------------

    _validate_limit(top_k, rrf_k)

    dense_ids = _validate_vector_candidates(
        dense_candidates,
        DenseSearchCandidate,
        "Dense",
    )

    sparse_ids = _validate_vector_candidates(
        sparse_candidates,
        SparseSearchCandidate,
        "BM25",
    )

    graph_keys = _validate_graph_candidates(
        graph_context,
    )

    # --------------------------------------------------
    # 2. 공통 검색 후보 구조 생성
    # --------------------------------------------------

    ranked_lists = (
        (
            "dense",
            [("chunk", point_id) for point_id in dense_ids],
        ),
        (
            "bm25",
            [("chunk", point_id) for point_id in sparse_ids],
        ),
        (
            "graph",
            graph_keys,
        ),
    )

    # --------------------------------------------------
    # 3. RRF 점수 계산
    # --------------------------------------------------

    scores: dict[tuple[str, str], float] = {}

    sources: dict[tuple[str, str], set[str]] = {}

    for method, candidates in ranked_lists:
        for rank, key in enumerate(candidates, start=1):
            rrf_score = 1.0 / (rrf_k + rank)

            scores[key] = scores.get(key, 0.0) + rrf_score

            sources.setdefault(key, set()).add(method)

    # --------------------------------------------------
    # 4. 중복 제거 및 검색 출처 보존
    # --------------------------------------------------

    results = []

    for (kind, item_id), score in scores.items():
        methods = tuple(
            method for method in METHOD_ORDER if method in sources[(kind, item_id)]
        )

        results.append(
            FusedSearchCandidate(
                kind=kind,
                item_id=item_id,
                score=score,
                methods=methods,
            )
        )

    # --------------------------------------------------
    # 5. 재순위화
    # --------------------------------------------------

    # 점수가 같으면 유형과 ID 순서로 정렬
    results.sort(
        key=lambda item: (
            -item.score,
            item.kind,
            item.item_id,
        )
    )

    # --------------------------------------------------
    # 6. 최종 후보 반환
    # --------------------------------------------------

    if top_k is not None:
        return results[:top_k]

    return results
