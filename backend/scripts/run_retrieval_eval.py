"""CASE-001 실제 Qdrant 검색 성능 비교."""

import json
from pathlib import Path

from ollama import Client as OllamaClient
from qdrant_client import QdrantClient

from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
)
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.dense_search import search_dense_candidates
from crimescene.retriever.hybrid_search import search_hybrid_candidates
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.retrieval_eval_dataset import (
    load_retrieval_evaluation_cases,
)
from crimescene.retriever.retrieval_metrics import (
    aggregate_retrieval_metrics,
    evaluate_retrieval_ranking,
)
from crimescene.retriever.sparse_search import search_sparse_candidates

CASE_ID = "CASE-001"
COLLECTION_NAME = "case001_rag_v1"

QDRANT_URL = "http://127.0.0.1:6333"
OLLAMA_URL = "http://127.0.0.1:11435"

METHODS = ("dense", "bm25", "hybrid")
QUERY_TYPES = ("keyword", "paraphrase", "multi_document")


def load_evaluation_data(root: Path):
    """신뢰 원본과 임시 평가 데이터셋을 불러온다."""

    matches = list(root.glob("*/data/access_policies.json"))

    if len(matches) != 1:
        raise ValueError("CASE-001 원본 경로를 확인하세요.")

    records = load_case001_hybrid_records(matches[0].parent)

    if len(records) != 116:
        raise ValueError(f"원본 문서 수가 올바르지 않습니다: {len(records)}")

    dataset_path = root / "retrieval_eval_provisional.jsonl"

    cases = load_retrieval_evaluation_cases(
        dataset_path,
        trusted_records=records,
    )

    if len(cases) != 29:
        raise ValueError(f"평가 질문은 29개여야 합니다: {len(cases)}")

    return records, cases


def search_all_methods(
    question,
    *,
    qdrant,
    embedder,
    encoder,
    source_type,
    case_id,
    character_id,
):
    """동일한 질문을 세 가지 검색 방식으로 실행한다."""

    common = {
        "client": qdrant,
        "source_type": source_type,
        "case_id": case_id,
        "character_id": character_id,
        "collection_name": COLLECTION_NAME,
    }

    dense_results = search_dense_candidates(
        question,
        embedder=embedder,
        top_k=10,
        **common,
    )

    bm25_results = search_sparse_candidates(
        question,
        encoder=encoder,
        top_k=10,
        **common,
    )

    hybrid_results = search_hybrid_candidates(
        question,
        embedder=embedder,
        encoder=encoder,
        candidate_k=30,
        top_k=10,
        rrf_k=60,
        **common,
    )

    return {
        "dense": [item.point_id for item in dense_results],
        "bm25": [item.point_id for item in bm25_results],
        "hybrid": [item.point_id for item in hybrid_results],
    }


def main():
    project_root = Path(__file__).resolve().parents[2]
    root = project_root / ".local" / "case001_v7_1"

    output_path = root / "retrieval_eval_results_provisional.json"

    # 기존 평가 결과를 실수로 덮어쓰지 않는다.
    if output_path.exists():
        raise FileExistsError("기존 평가 결과가 있습니다. 파일을 먼저 확인하세요.")

    records, cases = load_evaluation_data(root)

    print("=== CASE-001 RETRIEVAL EVALUATION ===")
    print("Trusted records:", len(records))
    print("Evaluation questions:", len(cases))
    print("Dataset status: PROVISIONAL")
    print()

    # Qdrant 연결
    qdrant = QdrantClient(
        url=QDRANT_URL,
        timeout=60,
    )

    try:
        # 실제 저장된 데이터 수 확인
        point_count = qdrant.count(
            collection_name=COLLECTION_NAME,
            exact=True,
        ).count

        print("Qdrant points:", point_count)

        if point_count != len(records):
            raise ValueError("Qdrant 데이터 수와 신뢰 원본 수가 다릅니다.")

        # CPU Ollama 서버 연결
        ollama_client = OllamaClient(
            host=OLLAMA_URL,
            timeout=600,
        )

        # 임베딩 모델 존재 확인
        ollama_client.show("bge-m3")

        embedder = OllamaEmbedder(
            model="bge-m3",
            vector_size=1024,
            client=ollama_client,
        )

        encoder = KoreanBM25Encoder()

        metric_rows = {method: [] for method in METHODS}

        type_metric_rows = {
            query_type: {method: [] for method in METHODS} for query_type in QUERY_TYPES
        }

        details = []

        print()
        print("=== SEARCH EVALUATION START ===")

        # 29개 질문을 순서대로 평가
        for index, case in enumerate(cases, start=1):
            if case.case_id != CASE_ID:
                raise ValueError(f"{case.question_id}: 사건 ID 불일치")

            if case.query_type not in QUERY_TYPES:
                raise ValueError(f"{case.question_id}: 질문 유형 불일치")

            results = search_all_methods(
                case.question,
                qdrant=qdrant,
                embedder=embedder,
                encoder=encoder,
                source_type=case.source_type,
                case_id=case.case_id,
                character_id=case.character_id,
            )

            scores_by_method = {}

            for method in METHODS:
                scores = evaluate_retrieval_ranking(
                    results[method],
                    case.relevant_point_ids,
                )

                metric_rows[method].append(scores)

                type_metric_rows[case.query_type][method].append(scores)

                scores_by_method[method] = scores

            # 원본 본문과 질문 텍스트는 결과에 기록하지 않는다.
            details.append(
                {
                    "question_id": case.question_id,
                    "query_type": case.query_type,
                    "source_type": case.source_type,
                    "character_id": case.character_id,
                    "relevant_point_ids": list(case.relevant_point_ids),
                    "retrieved_point_ids": results,
                    "metrics": scores_by_method,
                }
            )

            print(
                f"[{index}/{len(cases)}] {case.question_id} ({case.query_type}) PASSED",
                flush=True,
            )

        # 전체 평균
        summary = {
            method: aggregate_retrieval_metrics(metric_rows[method])
            for method in METHODS
        }

        # 질문 유형별 평균
        by_query_type = {
            query_type: {
                method: aggregate_retrieval_metrics(
                    type_metric_rows[query_type][method]
                )
                for method in METHODS
            }
            for query_type in QUERY_TYPES
        }

        # 결과 저장
        report = {
            "case_id": CASE_ID,
            "collection": COLLECTION_NAME,
            "dataset_status": "provisional",
            "gold_labels_confirmed": False,
            "trusted_records": len(records),
            "question_count": len(cases),
            "summary": summary,
            "by_query_type": by_query_type,
            "details": details,
        }

        with output_path.open("x", encoding="utf-8") as file:
            json.dump(
                report,
                file,
                ensure_ascii=False,
                indent=2,
            )

        # 콘솔에는 집계 점수만 표시
        print()
        print("=== OVERALL RESULTS ===")

        print(
            f"{'Method':<10}"
            f"{'Recall@5':>12}"
            f"{'Recall@10':>12}"
            f"{'MRR@10':>12}"
            f"{'nDCG@10':>12}"
        )

        for method, scores in summary.items():
            print(
                f"{method:<10}"
                f"{scores['recall_at_5']:>12.4f}"
                f"{scores['recall_at_10']:>12.4f}"
                f"{scores['mrr_at_10']:>12.4f}"
                f"{scores['ndcg_at_10']:>12.4f}"
            )

        print()
        print("=== RESULTS BY QUERY TYPE ===")

        for query_type, method_scores in by_query_type.items():
            print(f"\n[{query_type}]")

            for method, scores in method_scores.items():
                print(
                    f"{method:<10} "
                    f"Recall@5={scores['recall_at_5']:.4f} "
                    f"nDCG@10={scores['ndcg_at_10']:.4f}"
                )

        print()
        print("Gold labels: NOT CONFIRMED")
        print("Output:", output_path)
        print("RETRIEVAL EVALUATION PASSED")

    finally:
        qdrant.close()


if __name__ == "__main__":
    main()
