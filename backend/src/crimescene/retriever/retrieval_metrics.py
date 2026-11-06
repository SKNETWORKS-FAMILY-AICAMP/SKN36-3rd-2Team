"""RAG 검색 결과의 순위 기반 평가 지표."""

from collections.abc import Mapping, Sequence
from math import isfinite, log2

METRIC_NAMES = (
    "recall_at_5",
    "recall_at_10",
    "mrr_at_10",
    "ndcg_at_10",
)


def _normalize_ranked_ids(
    retrieved_point_ids: Sequence[str],
) -> list[str]:
    """검색 결과의 UUID 중복을 제거하고 순서를 유지한다."""

    seen = set()
    ranked = []

    for point_id in retrieved_point_ids:
        if not isinstance(point_id, str) or not point_id.strip():
            raise ValueError("검색 결과 UUID가 올바르지 않습니다.")

        if point_id in seen:
            continue

        seen.add(point_id)
        ranked.append(point_id)

    return ranked


def _normalize_relevant_ids(
    relevant_point_ids: Sequence[str],
) -> set[str]:
    """정답 UUID를 집합으로 정규화한다."""

    if not relevant_point_ids:
        raise ValueError("정답 UUID가 하나 이상 필요합니다.")

    relevant = set()

    for point_id in relevant_point_ids:
        if not isinstance(point_id, str) or not point_id.strip():
            raise ValueError("정답 UUID가 올바르지 않습니다.")

        relevant.add(point_id)

    return relevant


def recall_at_k(
    ranked: Sequence[str],
    relevant: set[str],
    k: int,
) -> float:
    """상위 K개 결과에서 전체 정답 중 검색된 비율."""

    if k <= 0:
        raise ValueError("k는 1 이상이어야 합니다.")

    found = set(ranked[:k]) & relevant

    return len(found) / len(relevant)


def mrr_at_k(
    ranked: Sequence[str],
    relevant: set[str],
    k: int,
) -> float:
    """상위 K개에서 첫 정답의 역순위."""

    if k <= 0:
        raise ValueError("k는 1 이상이어야 합니다.")

    for rank, point_id in enumerate(ranked[:k], start=1):
        if point_id in relevant:
            return 1.0 / rank

    return 0.0


def ndcg_at_k(
    ranked: Sequence[str],
    relevant: set[str],
    k: int,
) -> float:
    """상위 K개에서 정답 문서의 순위를 고려한 검색 품질."""

    if k <= 0:
        raise ValueError("k는 1 이상이어야 합니다.")

    dcg = sum(
        1.0 / log2(rank + 1)
        for rank, point_id in enumerate(ranked[:k], start=1)
        if point_id in relevant
    )

    ideal_count = min(len(relevant), k)

    idcg = sum(1.0 / log2(rank + 1) for rank in range(1, ideal_count + 1))

    return dcg / idcg


def evaluate_retrieval_ranking(
    retrieved_point_ids: Sequence[str],
    relevant_point_ids: Sequence[str],
) -> dict[str, float]:
    """단일 평가 질문에 대한 검색 품질을 계산한다."""

    ranked = _normalize_ranked_ids(retrieved_point_ids)

    relevant = _normalize_relevant_ids(relevant_point_ids)

    return {
        "recall_at_5": recall_at_k(ranked, relevant, 5),
        "recall_at_10": recall_at_k(ranked, relevant, 10),
        "mrr_at_10": mrr_at_k(ranked, relevant, 10),
        "ndcg_at_10": ndcg_at_k(ranked, relevant, 10),
    }


def aggregate_retrieval_metrics(
    metric_rows: Sequence[Mapping[str, float]],
) -> dict[str, float]:
    """여러 평가 질문의 검색 점수를 평균한다."""

    if not metric_rows:
        raise ValueError("평가 결과가 비어 있습니다.")

    totals = dict.fromkeys(METRIC_NAMES, 0.0)

    for row in metric_rows:
        if set(row) != set(METRIC_NAMES):
            raise ValueError("평가 지표 구성이 올바르지 않습니다.")

        for metric_name in METRIC_NAMES:
            value = row[metric_name]

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"{metric_name}: 점수가 올바르지 않습니다.")

            totals[metric_name] += value

    count = len(metric_rows)

    return {metric_name: total / count for metric_name, total in totals.items()}
