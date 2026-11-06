"""Dense 및 Sparse 검색 결과를 RRF로 결합한다."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from crimescene.retriever.dense_search import (
    DenseSearchCandidate,
)
from crimescene.retriever.sparse_search import (
    SparseSearchCandidate,
)

DEFAULT_RRF_K = 60
DEFAULT_TOP_K = 10


@dataclass(frozen=True, slots=True)
class HybridSearchCandidate:
    """접근 권한 검증 전의 Hybrid 검색 후보."""

    point_id: str
    score: float


def fuse_rrf_candidates(
    dense_candidates: Sequence[DenseSearchCandidate],
    sparse_candidates: Sequence[SparseSearchCandidate],
    *,
    top_k: int = DEFAULT_TOP_K,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[HybridSearchCandidate]:
    """Dense 및 Sparse 검색 결과를 RRF로 통합한다.

    Args:
        dense_candidates: Dense 검색 결과 (점수 내림차순)
        sparse_candidates: BM25 검색 결과 (점수 내림차순)
        top_k: 최종 반환 개수
        rrf_k: RRF 순위 보정 상수

    Returns:
        UUID와 RRF 점수만 포함한 검색 후보

    주의:
        검색 후보는 공개 가능한 문서가 아니다.
        LLM 전달 전 GameState 접근 권한 검사가 필요하다.
    """

    # 1. 입력 타입 검증
    if isinstance(dense_candidates, (str, bytes)) or not isinstance(
        dense_candidates, Sequence
    ):
        raise TypeError("Dense 검색 결과는 시퀀스여야 합니다.")

    if isinstance(sparse_candidates, (str, bytes)) or not isinstance(
        sparse_candidates, Sequence
    ):
        raise TypeError("Sparse 검색 결과는 시퀀스여야 합니다.")

    # 2. 검색 개수 검증
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k는 정수여야 합니다.")

    if not 1 <= top_k <= 100:
        raise ValueError("top_k는 1~100 사이여야 합니다.")

    # 3. RRF 상수 검증
    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int):
        raise TypeError("rrf_k는 정수여야 합니다.")

    if rrf_k <= 0:
        raise ValueError("rrf_k는 양수여야 합니다.")

    # 4. UUID별 RRF 점수 누적
    scores: dict[str, float] = {}

    for candidates, expected_type in (
        (dense_candidates, DenseSearchCandidate),
        (sparse_candidates, SparseSearchCandidate),
    ):
        seen_ids: set[str] = set()

        for rank, candidate in enumerate(candidates, start=1):
            # 검색 결과 타입 검증
            if not isinstance(candidate, expected_type):
                raise TypeError("검색 후보 타입이 올바르지 않습니다.")

            # UUID 검증
            point_id = candidate.point_id

            if not isinstance(point_id, str) or not point_id:
                raise ValueError("검색 후보 UUID가 올바르지 않습니다.")

            # 동일 검색 결과 내부 중복 차단
            if point_id in seen_ids:
                raise ValueError(f"중복된 검색 후보 UUID: {point_id}")

            seen_ids.add(point_id)

            # 원본 검색 점수 유효성 검증
            if not math.isfinite(candidate.score):
                raise ValueError("유효하지 않은 검색 점수입니다.")

            # RRF 점수 계산
            rrf_score = 1.0 / (rrf_k + rank)

            scores[point_id] = scores.get(point_id, 0.0) + rrf_score

    # 5. 최종 후보 생성
    results = [
        HybridSearchCandidate(
            point_id=point_id,
            score=score,
        )
        for point_id, score in scores.items()
    ]

    # 6. RRF 점수 내림차순 정렬
    # 점수가 같으면 UUID 순으로 정렬해 결과를 일정하게 유지
    results.sort(
        key=lambda item: (
            -item.score,
            item.point_id,
        )
    )

    return results[:top_k]
