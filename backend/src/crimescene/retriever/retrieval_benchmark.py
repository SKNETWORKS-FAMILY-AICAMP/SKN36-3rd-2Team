"""CASE-001 Dense/BM25/Hybrid 검색 성능 벤치마크."""

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ollama import Client
from qdrant_client import QdrantClient

from crimescene.db.neo4j_sync import find_source
from crimescene.ingest.case001_dataset import load_case001_hybrid_records
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.retrieval_metrics import (
    aggregate_retrieval_metrics,
)
from crimescene.retriever.search_comparison import (
    compare_search_methods,
    evaluate_search_comparison,
)
from crimescene.settings import settings


@dataclass(frozen=True, slots=True)
class ReviewQuestion:
    question_id: str
    question: str
    relevant_point_ids: tuple[str, ...]


def load_review_questions(
    path: Path,
    *,
    trusted_point_ids: set[str],
) -> list[ReviewQuestion]:
    """사람이 검토한 CSV를 평가 질문으로 변환한다."""

    if not path.is_file():
        raise FileNotFoundError(path)

    if not trusted_point_ids:
        raise ValueError("신뢰할 수 있는 문서가 없습니다.")

    required = {
        "question_id",
        "question",
        "point_id",
        "relevant",
    }

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("평가 CSV 필수 컬럼이 없습니다.")

        rows = list(reader)

    if not rows:
        raise ValueError("평가 CSV가 비어 있습니다.")

    groups = defaultdict(list)

    for row in rows:
        question_id = row["question_id"].strip()
        question = row["question"].strip()
        point_id = row["point_id"].strip()
        label = row["relevant"].strip()

        if not question_id or not question:
            raise ValueError("평가 질문이 비어 있습니다.")

        if point_id not in trusted_point_ids:
            raise ValueError(f"{question_id}: 신뢰 원본에 없는 UUID입니다.")

        if label not in {"0", "1"}:
            raise ValueError(f"{question_id}: relevant는 0 또는 1이어야 합니다.")

        groups[question_id].append((question, point_id, label))

    questions = []

    for question_id, group in sorted(groups.items()):
        texts = {item[0] for item in group}
        point_ids = [item[1] for item in group]

        if len(texts) != 1:
            raise ValueError(f"{question_id}: 질문 내용이 일치하지 않습니다.")

        if len(point_ids) != len(set(point_ids)):
            raise ValueError(f"{question_id}: 중복 UUID가 있습니다.")

        # 전체 신뢰 문서를 판정했는지 확인
        if set(point_ids) != trusted_point_ids:
            raise ValueError(f"{question_id}: 평가하지 않은 문서가 있습니다.")

        relevant = tuple(point_id for _, point_id, label in group if label == "1")

        if not relevant:
            raise ValueError(f"{question_id}: 정답 문서가 없습니다.")

        questions.append(
            ReviewQuestion(
                question_id=question_id,
                question=next(iter(texts)),
                relevant_point_ids=relevant,
            )
        )

    return questions


def evaluate_questions(questions, search_fn):
    """동일한 질문으로 검색 방식별 성능을 비교한다."""

    if not questions:
        raise ValueError("평가 질문이 없습니다.")

    metric_rows = {
        "dense": [],
        "bm25": [],
        "hybrid": [],
    }

    details = []

    for item in questions:
        result = search_fn(item.question)

        if result.query != item.question:
            raise ValueError(f"{item.question_id}: 검색 질문이 일치하지 않습니다.")

        metrics = evaluate_search_comparison(
            result,
            item.relevant_point_ids,
        )

        for method, values in metrics.items():
            metric_rows[method].append(values)

        details.append(
            {
                "question_id": item.question_id,
                "relevant_count": len(item.relevant_point_ids),
                "metrics": metrics,
            }
        )

    averages = {
        method: aggregate_retrieval_metrics(rows)
        for method, rows in metric_rows.items()
    }

    return details, averages


def main():
    parser = argparse.ArgumentParser(description="CASE-001 retrieval benchmark")

    parser.add_argument(
        "--root",
        type=Path,
        default=Path("../.local/case001_v7_1"),
    )

    parser.add_argument(
        "--review",
        type=Path,
        default=Path("../.local/issue17_search_full_review.csv"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../.local/issue17_benchmark_results.json"),
    )

    parser.add_argument(
        "--candidate-k",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    if not 1 <= args.top_k <= args.candidate_k <= 100:
        parser.error("1 <= top-k <= candidate-k <= 100이어야 합니다.")

    data_dir = find_source(
        args.root,
        "access_policies.json",
    ).parent

    records = load_case001_hybrid_records(data_dir)

    trusted_point_ids = {
        record.chunk.point_id
        for record in records
        if (
            record.chunk.case_id == "CASE-001"
            and record.chunk.source_type == "player_document"
        )
    }

    questions = load_review_questions(
        args.review,
        trusted_point_ids=trusted_point_ids,
    )

    client = QdrantClient(url=settings.qdrant_url)

    try:
        embedder = OllamaEmbedder(client=Client(host=settings.ollama_base_url))

        encoder = KoreanBM25Encoder()

        def search_fn(query):
            return compare_search_methods(
                query,
                client=client,
                embedder=embedder,
                encoder=encoder,
                source_type="player_document",
                candidate_k=args.candidate_k,
                top_k=args.top_k,
            )

        details, averages = evaluate_questions(
            questions,
            search_fn,
        )

    finally:
        client.close()

    report = {
        "case_id": "CASE-001",
        "question_count": len(questions),
        "candidate_k": args.candidate_k,
        "top_k": args.top_k,
        "averages": averages,
        "details": details,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 72)
    print("CASE-001 RETRIEVAL BENCHMARK")
    print("=" * 72)
    print(f"Questions: {len(questions)}")
    print(f"Candidate K: {args.candidate_k}")
    print(f"Top K: {args.top_k}")

    print()
    print(
        f"{'METHOD':<10}{'RECALL@5':>12}{'RECALL@10':>12}{'MRR@10':>12}{'NDCG@10':>12}"
    )

    for method, values in averages.items():
        print(
            f"{method.upper():<10}"
            f"{values['recall_at_5']:>12.3f}"
            f"{values['recall_at_10']:>12.3f}"
            f"{values['mrr_at_10']:>12.3f}"
            f"{values['ndcg_at_10']:>12.3f}"
        )

    print()
    print(f"Saved: {args.output.resolve()}")
    print("[PASS] Benchmark completed")


if __name__ == "__main__":
    main()
